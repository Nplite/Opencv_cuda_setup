#!/usr/bin/python3

import sys
import gi
gi.require_version('GObject', '2.0')
gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst

from common.bus_call import bus_call

import pyds
import cv2
import numpy as np
import threading

PGIE_CLASS_ID_VEHICLE = 0
PGIE_CLASS_ID_BICYCLE = 1
PGIE_CLASS_ID_PERSON = 2
PGIE_CLASS_ID_ROADSIGN = 3

class MultiRTSPStreamer:
    def __init__(self, rtsp_urls):
        """
        Initialize DeepStream pipeline for multiple RTSP streams
        
        :param rtsp_urls: List of RTSP stream URLs
        """
        self.rtsp_urls = rtsp_urls
        self.pipelines = []
        self.loops = []
        self.capture_threads = []
        self.caps = []

        # Standard GStreamer initialization
        GObject.threads_init()
        Gst.init(None)

    def create_pipeline(self, rtsp_url, stream_id):
        """
        Create a DeepStream pipeline for a single RTSP stream
        
        :param rtsp_url: RTSP stream URL
        :param stream_id: Unique identifier for the stream
        :return: Tuple of (pipeline, cap, loop)
        """
        # Open video capture
        cap = cv2.VideoCapture(rtsp_url)
        if not cap.isOpened():
            print(f"Can't open input frame for stream {stream_id}. Exiting...")
            return None

        # Get frame dimensions
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Create pipeline
        pipeline = Gst.Pipeline()

        # Create appsrc element
        appsource = Gst.ElementFactory.make("appsrc", f"opencv-source-{stream_id}")
        if not appsource:
            sys.stderr.write(f" Unable to create Source for stream {stream_id}\n")
            return None

        # Video converters and filters
        nvvideoconvert = Gst.ElementFactory.make("nvvideoconvert", f"nv-videoconv-{stream_id}")
        caps_filter = Gst.ElementFactory.make("capsfilter", f"capsfilter-{stream_id}")

        # Create nvstreammux instance to form batches from one or more sources
        streammux = Gst.ElementFactory.make("nvstreammux", f"Stream-muxer-{stream_id}")
        
        # Primary inference engine
        pgie = Gst.ElementFactory.make("nvinfer", f"primary-inference-{stream_id}")
        
        # Video converter
        nvvidconv = Gst.ElementFactory.make("nvvideoconvert", f"convertor-{stream_id}")
        
        # On-screen display
        nvosd = Gst.ElementFactory.make("nvdsosd", f"nvosd-{stream_id}")
        
        # Sink
        sink = Gst.ElementFactory.make("nveglglessink", f"nvvideo-renderer-{stream_id}")

        # Create main loop
        loop = GObject.MainLoop()

        # Set properties
        caps1 = Gst.Caps.from_string(f"video/x-raw,format=RGBA,width={width},height={height},framerate=30/1")
        caps2 = Gst.Caps.from_string(f"video/x-raw(memory:NVMM),format=NV12,width={width},height={height},framerate=30/1")
        
        appsource.set_property('caps', caps1)
        appsource.set_property()
        caps_filter.set_property('caps', caps2)

        streammux.set_property('width', width)
        streammux.set_property('height', height)
        streammux.set_property('batch-size', 1)
        streammux.set_property('batched-push-timeout', 4000000)
        
        pgie.set_property('config-file-path', "opencv/dstest1_pgie_config.txt")

        # Add elements to pipeline
        pipeline.add(appsource)
        pipeline.add(nvvideoconvert)
        pipeline.add(caps_filter)
        pipeline.add(streammux)
        pipeline.add(pgie)
        pipeline.add(nvvidconv)
        pipeline.add(nvosd)
        pipeline.add(sink)

        # Link elements
        appsource.link(nvvideoconvert)
        nvvideoconvert.link(caps_filter)

        # Get pads and link
        sinkpad = streammux.get_request_pad(f"sink_{stream_id}")
        srcpad = caps_filter.get_static_pad("src")
        srcpad.link(sinkpad)

        streammux.link(pgie)
        pgie.link(nvvidconv)
        nvvidconv.link(nvosd)
        nvosd.link(sink)

        # Create thread for frame pushing
        def cb_need_data(appsource, _size, user_data):
            nonlocal cap
            ret, frame = cap.read()
            if not ret:
                appsource.emit("end-of-stream")
                return

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
            appsource.emit("push-buffer", Gst.Buffer.new_wrapped(frame.tobytes()))

        appsource.connect("need-data", cb_need_data, None)

        return pipeline, cap, loop

    def run(self):
        """
        Run DeepStream pipelines for all RTSP streams
        """
        for idx, rtsp_url in enumerate(self.rtsp_urls):
            # Create pipeline for each stream
            pipeline_info = self.create_pipeline(rtsp_url, idx)
            if not pipeline_info:
                print(f"Failed to create pipeline for stream {idx}")
                continue

            pipeline, cap, loop = pipeline_info
            
            # Set pipeline to playing state
            pipeline.set_state(Gst.State.PLAYING)
            
            # Set up bus
            bus = pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", bus_call, loop)

            # Store for later cleanup
            self.pipelines.append(pipeline)
            self.loops.append(loop)
            self.caps.append(cap)

        # Run all loops
        for loop in self.loops:
            loop.run()

    def cleanup(self):
        """
        Clean up resources
        """
        # Stop and clean up pipelines
        for pipeline in self.pipelines:
            pipeline.set_state(Gst.State.NULL)
        
        # Release video captures
        for cap in self.caps:
            cap.release()

def main():
    # Check for correct usage
    if len(sys.argv) < 2:
        sys.stderr.write("usage: %s <rtsp_url1> <rtsp_url2> ...\n" % sys.argv[0])
        sys.exit(1)

    # Get RTSP URLs from command line arguments
    rtsp_urls = sys.argv[1:]

    try:
        # Create and run multi-stream processor
        streamer = MultiRTSPStreamer(rtsp_urls)
        streamer.run()
    except KeyboardInterrupt:
        print("Interrupted by user, cleaning up...")
    finally:
        streamer.cleanup()

if __name__ == '__main__':
    main()