import gi
import sys

gi.require_version('Gst', '1.0')
gi.require_version('GObject', '2.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gst, GLib

def create_gpu_optimized_pipeline(rtsp_urls):
    """Create a fully GPU-optimized GStreamer pipeline with nvdsosd."""
    # Initialize pipeline
    pipeline = Gst.Pipeline.new("gpu-multi-stream")

    # Create stream multiplexer (batching multiple streams)
    streammux = Gst.ElementFactory.make("nvstreammux", "stream-muxer")
    streammux.set_property("batch-size", len(rtsp_urls))
    streammux.set_property("batched-push-timeout", 15000)
    streammux.set_property("width", 1920)
    streammux.set_property("height", 1080)
    streammux.set_property("live-source", True)
    streammux.set_property("enable-padding", False)  # Disable padding
    pipeline.add(streammux)

    # Process each stream
    for stream_index, rtsp_url in enumerate(rtsp_urls):
        # RTSP Source (RTSP source will still be CPU-based)
        rtsp_src = Gst.ElementFactory.make("rtspsrc", f"rtsp-src-{stream_index}")
        rtsp_src.set_property("location", rtsp_url)
        rtsp_src.set_property("latency", 50)
        rtsp_src.set_property("drop-on-latency", True)

        # H.264 Depayloader (GPU-accelerated)
        depay = Gst.ElementFactory.make("rtph264depay", f"depay-{stream_index}")

        # GPU-based Decoder (H.264 decoding on GPU)
        decoder = Gst.ElementFactory.make("nvv4l2decoder", f"decoder-{stream_index}")
        decoder.set_property("gpu-id", 0)

        # GPU-based Video Converter
        converter = Gst.ElementFactory.make("nvvideoconvert", f"converter-{stream_index}")
        
        # Caps Filter for consistent GPU format
        caps_filter = Gst.ElementFactory.make("capsfilter", f"caps-{stream_index}")
        caps_filter.set_property("caps", Gst.Caps.from_string(
            "video/x-raw(memory:NVMM), width=1920, height=1080"
        ))

        # Add elements to pipeline
        for elem in [rtsp_src, depay, decoder, converter, caps_filter]:
            pipeline.add(elem)

        # Dynamic pad handling for RTSP Source
        rtsp_src.connect("pad-added", lambda src, pad, d=depay: 
            pad.link(d.get_static_pad("sink")) if not d.get_static_pad("sink").is_linked() else None)

        # Link elements: RTSP source → Depayloader → Decoder → Converter → Caps Filter
        Gst.Element.link_many(depay, decoder, converter, caps_filter)

        # Request stream muxer pad and link
        sinkpad = streammux.request_pad_simple(f"sink_{stream_index}")
        caps_filter.get_static_pad("src").link(sinkpad)

    # GPU-based Tiler for multi-stream layout
    tiler = Gst.ElementFactory.make("nvmultistreamtiler", "gpu-tiler")
    rows = int(len(rtsp_urls) ** 0.5) + (1 if len(rtsp_urls) % int(len(rtsp_urls) ** 0.5) else 0)
    cols = (len(rtsp_urls) + rows - 1) // rows
    
    tiler.set_property("rows", rows)
    tiler.set_property("columns", cols)
    tiler.set_property("width", 3840)
    tiler.set_property("height", 2160)
    pipeline.add(tiler)

    # GPU-based On-Screen Display (OSD)
    osd = Gst.ElementFactory.make("nvdsosd", "gpu-osd")
    osd.set_property("gpu-id", 0)
    osd.set_property("process-mode", 1) 
    pipeline.add(osd)

    # GPU-based sink for rendering
    sink = Gst.ElementFactory.make("nveglglessink", "gpu-sink")
    sink.set_property("sync", False)
    sink.set_property("qos", True)
    sink.set_property("max-lateness", -1)
    pipeline.add(sink)

    # Link final components: StreamMuxer → Tiler → OSD → Sink
    streammux.link(tiler)
    tiler.link(osd)
    osd.link(sink)

    return pipeline

def main():
    Gst.init(None)

    # RTSP URLs (can be changed to your actual camera URLs)
    rtsp_urls = [
        "rtsp://ProjectTheft2024:Theft%402024@103.194.88.114/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@115.244.177.86/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@103.194.88.114/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@115.244.177.86/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@103.194.88.114/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@115.244.177.86/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@103.194.88.114/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@115.244.177.86/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@103.194.88.114/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@115.244.177.86/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@103.194.88.114/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@115.244.177.86/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@103.194.88.114/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@115.244.177.86/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@103.194.88.114/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@115.244.177.86/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@103.194.88.114/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@115.244.177.86/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@103.194.88.114/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@115.244.177.86/cam/realmonitor?channel=1&subtype=0",      

    ]

    # Create GPU-optimized pipeline
    pipeline = create_gpu_optimized_pipeline(rtsp_urls)
    
    if not pipeline:
        print("Failed to create pipeline")
        return

    # Start pipeline
    pipeline.set_state(Gst.State.PLAYING)
    print("Pipeline Started")

    # Run main loop
    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        print("Stopping pipeline...")
        pipeline.set_state(Gst.State.NULL)

if __name__ == "__main__":
    main()