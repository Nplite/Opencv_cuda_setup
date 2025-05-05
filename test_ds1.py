import sys
import gi
import math
import queue
from typing import List, Optional

gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GLib, GObject

# Initialize threading and GStreamer thread safety
GObject.threads_init()
Gst.init(None)

class MultiStreamProcessor:
    def __init__(self, uris: List[str], width: int = 360, height: int = 240):
        """
        Initialize multi-stream video processing pipeline
        
        Args:
            uris (List[str]): List of video stream URIs
            width (int): Output width for streams
            height (int): Output height for streams
        """
        self.uris = uris
        self.width = width
        self.height = height
        self.pipeline: Optional[Gst.Pipeline] = None
        self.loop: Optional[GLib.MainLoop] = None
        self.error_queue = queue.Queue()

    def _create_source_bin(self, index: int, uri: str) -> Gst.Bin:
        """Create a source bin for RTSP/video stream with enhanced error handling"""
        bin_name = f"source-bin-{index}"
        source_bin = Gst.Bin.new(bin_name)
        
        try:
            uri_decode_bin = Gst.ElementFactory.make("uridecodebin", "uri-decode-bin")
            uri_decode_bin.set_property("uri", uri)
            uri_decode_bin.set_property("buffer-size", 8192)  # Increased buffer size
            uri_decode_bin.connect("pad-added", self._on_pad_added, source_bin)
            uri_decode_bin.connect("source-setup", self._on_source_setup)
            
            source_bin.add(uri_decode_bin)
            bin_pad = source_bin.add_pad(Gst.GhostPad.new_no_target("src", Gst.PadDirection.SRC))
            
            return source_bin
        except Exception as e:
            self.error_queue.put(f"Source bin creation error: {e}")
            return None

    def _on_source_setup(self, uridecodebin, source):
        """Configure stream source with timeout and buffer settings"""
        if hasattr(source, 'set_property'):
            source.set_property('timeout', 5)  # 5 second connection timeout
            source.set_property('latency', 1000)  # Reduced latency

    def _on_pad_added(self, decodebin, decoder_src_pad, source_bin):
        """Enhanced pad linking with more robust error handling"""
        try:
            caps = decoder_src_pad.get_current_caps()
            gstname = caps.get_structure(0).get_name()
            
            if "video" in gstname:
                bin_ghost_pad = source_bin.get_static_pad("src")
                bin_ghost_pad.set_target(decoder_src_pad)
        except Exception as e:
            self.error_queue.put(f"Pad linking error: {e}")

    def _create_pipeline(self) -> bool:
        """Create optimized GStreamer pipeline"""
        try:
            # Pipeline creation with error checking
            self.pipeline = Gst.Pipeline.new("video-pipeline")
            
            # Stream multiplexer with performance tuning
            streammux = Gst.ElementFactory.make("nvstreammux", "streammux")
            streammux.set_property("width", self.width)
            streammux.set_property("height", self.height)
            streammux.set_property("batch-size", len(self.uris))
            streammux.set_property("gpu-id", 0)  # Use first GPU
            streammux.set_property("live-source", True)
            
            self.pipeline.add(streammux)

            # Add sources to pipeline
            for i, uri in enumerate(self.uris):
                source_bin = self._create_source_bin(i, uri)
                if source_bin is None:
                    continue
                
                self.pipeline.add(source_bin)
                pad_name = f"sink_{i}"
                sink_pad = streammux.request_pad_simple(pad_name)
                src_pad = source_bin.get_static_pad("src")
                src_pad.link(sink_pad)

            # Tiler with dynamic row/column calculation
            tiler = Gst.ElementFactory.make("nvmultistreamtiler", "tiler")
            rows = max(1, int(math.sqrt(len(self.uris))))
            columns = max(1, int(math.ceil(len(self.uris) / rows)))
            
            tiler.set_property("rows", rows)
            tiler.set_property("columns", columns)
            tiler.set_property("width", self.width)
            tiler.set_property("height", self.height)

            # Hardware-accelerated video conversion
            nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "nvvidconv")
            nvvidconv.set_property("gpu-id", 0)

            # Output sink
            sink = Gst.ElementFactory.make("nveglglessink", "sink")
            sink.set_property("sync", False)  # Disable sync for lower latency

            # Add and link elements
            for element in [tiler, nvvidconv, sink]:
                self.pipeline.add(element)

            # Pipeline linking
            streammux.link(tiler)
            tiler.link(nvvidconv)
            nvvidconv.link(sink)

            return True
        
        except Exception as e:
            self.error_queue.put(f"Pipeline creation error: {e}")
            return False

    def run(self):
        """Run the video processing pipeline"""
        if not self._create_pipeline():
            print("Failed to create pipeline")
            return

        # Bus message handling
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._bus_call)

        # Start pipeline
        self.pipeline.set_state(Gst.State.PLAYING)
        
        # Run main loop
        self.loop = GLib.MainLoop()
        try:
            self.loop.run()
        except KeyboardInterrupt:
            pass
        finally:
            self.pipeline.set_state(Gst.State.NULL)

    def _bus_call(self, bus, message, *args):
        """Enhanced bus message handling"""
        msg_type = message.type

        if msg_type == Gst.MessageType.EOS:
            print("End of stream")
            self.loop.quit()
        
        elif msg_type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Error: {err}, Debug: {debug}")
            self.loop.quit()
        
        return True

def main(args):
    if len(args) < 2:
        print(f"Usage: {args[0]} <uri1> [uri2] ... [uriN]")
        sys.exit(1)
    
    processor = MultiStreamProcessor(args[1:])
    processor.run()

if __name__ == '__main__':
    sys.exit(main(sys.argv))