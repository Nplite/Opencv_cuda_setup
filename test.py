import sys
import gi
import argparse
gi.require_version("Gst", "1.0")
from gi.repository import Gst, GLib

# Initialize GStreamer
Gst.init(None)

def create_source_bin(index, uri):
    """
    Create a source bin for a URI input (RTSP) stream using GPU-accelerated decoding.
    """
    print(f"Creating source bin for stream {index}")
    nbin = Gst.Bin.new(f"source-bin-{index}")
    if not nbin:
        sys.stderr.write("Unable to create source bin\n")
        return None
    
    # Create URI decode bin
    uri_decode_bin = Gst.ElementFactory.make("uridecodebin", f"uri-decode-bin-{index}")
    if not uri_decode_bin:
        sys.stderr.write("Unable to create uri decode bin\n")
        return None
    
    uri_decode_bin.set_property("uri", uri)
    uri_decode_bin.connect("pad-added", cb_newpad, nbin)

    # Add URI decode bin to the source bin
    nbin.add(uri_decode_bin)
    
    # H.264 Depayloader (GPU-accelerated)
    depay = Gst.ElementFactory.make("rtph264depay", f"depay-{index}")
    if not depay:
        sys.stderr.write(f"Unable to create rtph264depay for stream {index}\n")
        return None
    nbin.add(depay)

    # H.264 Parser (necessary to prepare stream for decoding)
    parser = Gst.ElementFactory.make("h264parse", f"h264parse-{index}")
    if not parser:
        sys.stderr.write(f"Unable to create h264parse for stream {index}\n")
        return None
    nbin.add(parser)

    # GPU-accelerated decoder
    decoder = Gst.ElementFactory.make("nvv4l2decoder", f"nv-decoder-{index}")
    if not decoder:
        sys.stderr.write(f"Unable to create nvv4l2decoder for stream {index}\n")
        return None
    decoder.set_property("gpu-id", 0)
    decoder.set_property("skip-frames", 0)
    nbin.add(decoder)

    # Link the depayloader to the parser, and the parser to the decoder
    depay.link(parser)
    parser.link(decoder)

    # Video converter for GPU
    nvconv = Gst.ElementFactory.make("nvvideoconvert", f"nvconv-{index}")
    if not nvconv:
        sys.stderr.write(f"Unable to create nvvideoconvert for stream {index}\n")
        return None
    nbin.add(nvconv)

    # Link the decoder to video converter
    decoder.link(nvconv)

    # Create a ghost pad for the source bin
    bin_pad = Gst.GhostPad.new_no_target("src", Gst.PadDirection.SRC)
    nbin.add_pad(bin_pad)

    return nbin

def cb_newpad(decodebin, decoder_src_pad, data):
    """
    Callback function to handle new pads from the URI decodebin.
    """
    caps = decoder_src_pad.get_current_caps()
    gststruct = caps.get_structure(0)
    gstname = gststruct.get_name()
    source_bin = data
    features = caps.get_features(0)
    print(f"New pad added: {gstname}")  # Log pad info
    
    if gstname.find("video") != -1 and features.contains("memory:NVMM"):
        bin_ghost_pad = source_bin.get_static_pad("src")
        if not bin_ghost_pad.set_target(decoder_src_pad):
            sys.stderr.write("Failed to link decoder src pad to source bin ghost pad\n")
    else:
        sys.stderr.write("Error: Decodebin did not pick NVIDIA decoder plugin.\n")

def make_element(element_name, i):
    """
    Create a GStreamer element with a unique name based on its index.
    """
    element = Gst.ElementFactory.make(element_name, f"{element_name}-{i}")
    if not element:
        sys.stderr.write(f"Unable to create {element_name}\n")
    return element

def bus_call(bus, message, loop):
    """
    Callback to handle messages from the GStreamer bus.
    """
    t = message.type
    if t == Gst.MessageType.EOS:
        print("End of Stream")
        loop.quit()
    elif t == Gst.MessageType.ERROR:
        err, deb = message.parse_error()
        print(f"Error: {err}: {deb}")
        loop.quit()
    return True

def main():
    # Hardcoded RTSP stream URIs (replace these with your actual URIs)
    input_sources = [
        # "rtsp://ProjectTheft2024:Theft%402024@103.106.195.202:554/cam/realmonitor?channel=1&subtype=0",
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
        "rtsp://ProjectTheft2024:Theft%402024@103.194.88.114/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@115.244.177.86/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@103.194.88.114/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@115.244.177.86/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@103.194.88.114/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@115.244.177.86/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@103.194.88.114/cam/realmonitor?channel=1&subtype=0",
        "rtsp://ProjectTheft2024:Theft%402024@115.244.177.86/cam/realmonitor?channel=1&subtype=0",

        
   ]
    
    number_sources = len(input_sources)
    
    # Create the pipeline
    pipeline = Gst.Pipeline.new("pipeline")
    if not pipeline:
        sys.stderr.write("Unable to create pipeline\n")
        return
    
    # Create a streammux element
    streammux = Gst.ElementFactory.make("nvstreammux", "streammux")
    if not streammux:
        sys.stderr.write("Unable to create nvstreammux\n")
        return
    
    streammux.set_property("batch-size", number_sources)
    streammux.set_property("batched-push-timeout", 15000)
    streammux.set_property("width", 640)
    streammux.set_property("height", 480)
    streammux.set_property("live-source", True)
    streammux.set_property("enable-padding", False)

    pipeline.add(streammux)

    # Create source bins and add them to the pipeline
    for i in range(number_sources):
        uri_name = input_sources[i]
        source_bin = create_source_bin(i, uri_name)
        if not source_bin:
            sys.stderr.write(f"Unable to create source bin for stream {i}\n")
            continue
        
        pipeline.add(source_bin)
        
        # Request pad from the streammux and link to the source bin
        padname = f"sink_{i}"
        sinkpad = streammux.request_pad_simple(padname)
        if not sinkpad:
            sys.stderr.write(f"Unable to request pad for stream {i}\n")
            continue
        
        # Link the source bin's pad to the streammux
        srcpad = source_bin.get_static_pad("src")
        if not srcpad:
            sys.stderr.write(f"Unable to get source pad for stream {i}\n")
            continue
        
        srcpad.link(sinkpad)

    # Create the tiler element for arranging the streams
    tiler = Gst.ElementFactory.make("nvmultistreamtiler", "tiler")
    if not tiler:
        sys.stderr.write("Unable to create nvtiler\n")
        return
    
    rows = int(number_sources ** 0.5)
    cols = (number_sources + rows - 1) // rows 
    tiler.set_property("rows", rows)
    tiler.set_property("columns", cols)
    tiler.set_property("width", 3840)
    tiler.set_property("height", 2160)

    pipeline.add(tiler)

    # Link the streammux to the tiler
    streammux.link(tiler)

    # Create the output sink element
    sink = make_element("nveglglessink", "gpu-sink")
    if not sink:
        sys.stderr.write("Unable to create output sink\n")
        return
    
    sink.set_property("sync", False)
    sink.set_property("qos", True)
    sink.set_property("max-lateness", -1)
    pipeline.add(sink)

    # Link the tiler to the output sink
    tiler.link(sink)

    # Start the pipeline
    print("Starting pipeline with", number_sources, "streams")
    pipeline.set_state(Gst.State.PLAYING)
    
    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", bus_call, loop)
    
    try:
        loop.run()
    except:
        pass

    # Cleanup
    print("Exiting app")
    pipeline.set_state(Gst.State.NULL)

if __name__ == "__main__":
    main()