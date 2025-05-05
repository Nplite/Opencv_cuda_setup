import sys
import gi
import cv2
import json
from common.bus_call import bus_call
import pyds

# GStreamer setup
gi.require_version("Gst", "1.0")
gi.require_version("GstApp", "1.0")
from gi.repository import GLib, Gst

# Constants for classes
PGIE_CLASS_ID_VEHICLE = 0
PGIE_CLASS_ID_BICYCLE = 1
PGIE_CLASS_ID_PERSON = 2
PGIE_CLASS_ID_ROADSIGN = 3

# Dictionaries to manage OpenCV video captures and ROIs
caps = {}
stream_rois = {}

def motion_detection(frame, stream_id):
    """
    Detect motion within defined ROI using frame differencing.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    if not hasattr(motion_detection, 'prev_frames'):
        motion_detection.prev_frames = {}

    roi_x, roi_y, roi_w, roi_h = stream_rois.get(stream_id, (0, 0, gray.shape[1], gray.shape[0]))
    roi_gray = gray[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]

    if stream_id not in motion_detection.prev_frames:
        motion_detection.prev_frames[stream_id] = roi_gray
        return False

    frame_diff = cv2.absdiff(motion_detection.prev_frames[stream_id], roi_gray)
    _, thresh = cv2.threshold(frame_diff, 25, 255, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    motion_detected = any(cv2.contourArea(contour) > 500 for contour in contours)

    motion_detection.prev_frames[stream_id] = roi_gray
    return motion_detected

def cb_need_data(appsource, _size, stream_id):
    global caps, stream_rois

    if not hasattr(cb_need_data, 'frame_counters'):
        cb_need_data.frame_counters = {}

    if stream_id not in cb_need_data.frame_counters:
        cb_need_data.frame_counters[stream_id] = 0

    if stream_id not in caps:
        appsource.emit("end-of-stream")
        return

    ret, frame = caps[stream_id].read()
    if not ret:
        appsource.emit("end-of-stream")
        return

    cb_need_data.frame_counters[stream_id] += 1
    current_frame = cb_need_data.frame_counters[stream_id]

    frame = cv2.resize(frame, (640, 360))
    roi_x, roi_y, roi_w, roi_h = stream_rois.get(stream_id, (0, 0, frame.shape[1], frame.shape[0]))
    cv2.rectangle(frame, (roi_x, roi_y), (roi_x + roi_w, roi_y + roi_h), (0, 255, 0), 2)

    motion_detected = motion_detection(frame, stream_id)
    if motion_detected:
        print(f"Motion detected in stream {stream_id}")  # Print instead of visualizing motion

    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
    buffer = Gst.Buffer.new_wrapped(frame.tobytes())

    timestamp = current_frame * (1 / 10) * Gst.SECOND
    buffer.pts = timestamp
    buffer.duration = int(Gst.SECOND / 10)

    appsource.emit("push-buffer", buffer)

def osd_sink_pad_buffer_probe(pad, info, u_data):
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        return Gst.PadProbeReturn.OK

    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break

        l_frame = l_frame.next

    return Gst.PadProbeReturn.OK

def create_pipeline(stream_configs):
    global caps, stream_rois

    pipeline = Gst.Pipeline()
    if not pipeline:
        raise RuntimeError("Unable to create Pipeline")

    streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    if not streammux:
        raise RuntimeError("Unable to create Stream-muxer")

    # Create all elements, including queue elements
    pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
    queue1 = Gst.ElementFactory.make("queue", "queue1")
    nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "nvvideo-converter")
    queue2 = Gst.ElementFactory.make("queue", "queue2")
    nvosd = Gst.ElementFactory.make("nvdsosd", "on-screen-display")
    queue3 = Gst.ElementFactory.make("queue", "queue3")
    tiler = Gst.ElementFactory.make("nvmultistreamtiler", "tiler")
    queue4 = Gst.ElementFactory.make("queue", "queue4")
    sink = Gst.ElementFactory.make("nveglglessink", "egl-overlay")

    if not all([pgie, queue1, nvvidconv, queue2, nvosd, queue3, tiler, queue4, sink]):
        raise RuntimeError("Unable to create one or more elements")

    pipeline.add(streammux)
    pipeline.add(pgie)
    pipeline.add(queue1)
    pipeline.add(nvvidconv)
    pipeline.add(queue2)
    pipeline.add(nvosd)
    pipeline.add(queue3)
    pipeline.add(tiler)
    pipeline.add(queue4)
    pipeline.add(sink)

    # Configure tiler
    tiler.set_property("rows", 1)
    tiler.set_property("columns", len(stream_configs))
    tiler.set_property("width", 1280)
    tiler.set_property("height", 720)

    # Configure streammux
    streammux.set_property('width', 640)
    streammux.set_property('height', 360)
    streammux.set_property('batch-size', len(stream_configs))
    streammux.set_property('batched-push-timeout', 6000000)

    # Set PGIE configuration file
    pgie.set_property('config-file-path', "opencv/dstest1_pgie_config.txt")
    pgie.set_property('batch-size', len(stream_configs))

    # Link elements with queues
    streammux.link(pgie)
    pgie.link(queue1)
    queue1.link(nvvidconv)
    nvvidconv.link(queue2)
    queue2.link(tiler)
    tiler.link(queue3)
    queue3.link(nvosd)
    nvosd.link(queue4)
    queue4.link(sink)

    # Add and configure sources for each stream
    for i, stream_config in enumerate(stream_configs):
        uri = stream_config['uri']
        roi = stream_config['roi']

        stream_rois[i] = roi
        caps[i] = cv2.VideoCapture(uri)
        if not caps[i].isOpened():
            raise RuntimeError(f"Can't open input stream {uri}")

        appsource = Gst.ElementFactory.make("appsrc", f"opencv-source-{i}")
        caps_filter = Gst.ElementFactory.make("capsfilter", f"capsfilter-{i}")
        nvvidconv_src = Gst.ElementFactory.make("nvvideoconvert", f"nvvideo-converter-{i}")
        queue_src = Gst.ElementFactory.make("queue", f"queue-src-{i}")

        gst_caps = Gst.Caps.from_string("video/x-raw,format=RGBA,width=640,height=360,framerate=15/1")
        caps_filter.set_property('caps', gst_caps)

        appsource.set_property("caps", gst_caps)
        appsource.set_property("format", Gst.Format.TIME)
        appsource.set_property("is-live", True)
        appsource.set_property("stream-type", 0)

        pipeline.add(appsource)
        pipeline.add(caps_filter)
        pipeline.add(nvvidconv_src)
        pipeline.add(queue_src)

        appsource.link(caps_filter)
        caps_filter.link(nvvidconv_src)
        nvvidconv_src.link(queue_src)

        sinkpad = streammux.get_request_pad(f"sink_{i}")
        srcpad = queue_src.get_static_pad("src")
        srcpad.link(sinkpad)

        appsource.connect("need-data", cb_need_data, i)

    # Attach probe to on-screen display
    osd_sink_pad = nvosd.get_static_pad("sink")
    osd_sink_pad.add_probe(Gst.PadProbeType.BUFFER, osd_sink_pad_buffer_probe, None)

    return pipeline

def main(args):
    if len(args) < 2:
        sys.stderr.write("usage: %s <json_config_file>\n" % args[0])
        sys.exit(1)

    try:
        with open(args[1], 'r') as f:
            stream_configs = json.load(f)
    except Exception as e:
        sys.stderr.write(f"Error reading JSON configuration: {e}\n")
        sys.exit(1)

    Gst.init(None)

    try:
        pipeline = create_pipeline(stream_configs)
        pipeline.set_state(Gst.State.PLAYING)

        loop = GLib.MainLoop()
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", bus_call, loop)

        try:
            loop.run()
        except KeyboardInterrupt:
            pass

        pipeline.set_state(Gst.State.NULL)
    except Exception as e:
        sys.stderr.write(f"Pipeline error: {e}\n")
        sys.exit(1)

if __name__ == '__main__':
    sys.exit(main(sys.argv))