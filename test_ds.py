import gi
import sys

gi.require_version('Gst', '1.0')
gi.require_version('GObject', '2.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gst, GLib

def on_eos(bus, msg, loop, pipeline):
    """Handle End of Stream (EOS)"""
    print(f"Pipeline {pipeline.get_name()} reached End of Stream. Restarting...")
    pipeline.set_state(Gst.State.NULL)
    pipeline.set_state(Gst.State.PLAYING)

def on_error(bus, msg, loop, pipeline):
    """Handle pipeline errors"""
    err, debug = msg.parse_error()
    print(f"Error in pipeline {pipeline.get_name()}: {err.message}")
    if debug:
        print(f"Debug details: {debug}")
    # Restart the pipeline on error
    pipeline.set_state(Gst.State.NULL)
    pipeline.set_state(Gst.State.PLAYING)

def on_pad_added(src, new_pad, depay):
    """Handle dynamic pad addition from the RTSP source"""
    sink_pad = depay.get_static_pad("sink")
    if not sink_pad.is_linked():
        ret = new_pad.link(sink_pad)
        if ret != Gst.PadLinkReturn.OK:
            print(f"Failed to link new pad to depay: {ret}")
    else:
        print("Pad is already linked")

def create_pipeline(rtsp_url, stream_index):
    """Create a GStreamer pipeline for an RTSP stream"""
    pipeline = Gst.Pipeline.new(f"pipeline-{stream_index}")

    # Create pipeline elements
    rtsp_src = Gst.ElementFactory.make("rtspsrc", f"rtsp-src-{stream_index}")
    if not rtsp_src:
        print(f"Error: Failed to create rtspsrc for stream {stream_index}.")
        return None
    rtsp_src.set_property("location", rtsp_url)
    rtsp_src.set_property("latency", 200)
    rtsp_src.set_property("do-rtsp-keep-alive", True)

    depay = Gst.ElementFactory.make("rtph264depay", f"depay-{stream_index}")
    queue1 = Gst.ElementFactory.make("queue", f"queue1-{stream_index}")
    h264parse = Gst.ElementFactory.make("h264parse", f"h264-parse-{stream_index}")
    queue2 = Gst.ElementFactory.make("queue", f"queue2-{stream_index}")
    decoder = Gst.ElementFactory.make("nvv4l2decoder", f"decoder-{stream_index}")
    converter = Gst.ElementFactory.make("nvvideoconvert", f"converter-{stream_index}")
    caps_filter = Gst.ElementFactory.make("capsfilter", f"caps-filter-{stream_index}")
    sink = Gst.ElementFactory.make("nveglglessink", f"sink-{stream_index}")

    if not all([depay, queue1, h264parse, queue2, decoder, converter, caps_filter, sink]):
        print(f"Error: Failed to create elements for stream {stream_index}.")
        return None

    caps_filter.set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), width=640, height=480"))
    sink.set_property("sync", True)

    # Add elements to the pipeline
    pipeline.add(rtsp_src, depay, queue1, h264parse, queue2, decoder, converter, caps_filter, sink)

    # Link elements in the pipeline
    try:
        depay.link(queue1)
        queue1.link(h264parse)
        h264parse.link(queue2)
        queue2.link(decoder)
        decoder.link(converter)
        converter.link(caps_filter)
        caps_filter.link(sink)
    except Exception as e:
        print(f"Error: Failed to link elements for stream {stream_index}: {e}")
        return None

    # Handle dynamic pads from the RTSP source
    rtsp_src.connect("pad-added", lambda src, pad: on_pad_added(src, pad, depay))

    return pipeline


def check_pipeline_status(pipelines):
    """Periodically check the status of each pipeline"""
    for pipeline in pipelines:
        state_change_return, state, _ = pipeline.get_state(Gst.CLOCK_TIME_NONE)
        if state != Gst.State.PLAYING:
            print(f"Pipeline {pipeline.get_name()} is not playing, restarting...")
            pipeline.set_state(Gst.State.NULL)
            pipeline.set_state(Gst.State.PLAYING)
    return True  # Return True to keep the timeout active

def main():
    # Initialize GStreamer
    Gst.init(None)

    # RTSP URLs
    rtsp_urls = [
        "rtsp://ProjectTheft2024:Theft%402024@103.106.195.202/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@103.194.88.114/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@115.244.177.86/cam/realmonitor?channel=1&subtype=0",

    ]

    # Create a main event loop
    loop = GLib.MainLoop()

    # Create pipelines for each RTSP stream
    pipelines = []
    for i, url in enumerate(rtsp_urls):
        pipeline = create_pipeline(url, i)
        if pipeline:
            pipelines.append(pipeline)

    if not pipelines:
        print("No pipelines were successfully created. Exiting.")
        return

    # Bus to handle messages (errors, EOS, etc.)
    for pipeline in pipelines:
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", on_error, loop, pipeline)
        bus.connect("message::eos", on_eos, loop, pipeline)

    # Start all pipelines
    for pipeline in pipelines:
        pipeline.set_state(Gst.State.PLAYING)
        print(f"Pipeline {pipeline.get_name()} started.")

    # Set up a timer to check the pipeline status every 5 seconds
    GLib.timeout_add_seconds(5, check_pipeline_status, pipelines)

    try:
        loop.run()
    except KeyboardInterrupt:
        print("Interrupt received. Stopping pipelines...")

    # Clean up pipelines
    for pipeline in pipelines:
        pipeline.set_state(Gst.State.NULL)
        print(f"Pipeline {pipeline.get_name()} stopped.")

if __name__ == "__main__":
    main()