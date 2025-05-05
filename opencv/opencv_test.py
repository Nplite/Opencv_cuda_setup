import sys
import gi
import cv2
import json

gi.require_version("Gst", "1.0")
gi.require_version("GstApp", "1.0")
from gi.repository import GObject, Gst, GstApp

import pyds

# Constants for classes (same as original code)
PGIE_CLASS_ID_VEHICLE = 0
PGIE_CLASS_ID_BICYCLE = 1
PGIE_CLASS_ID_PERSON = 2
PGIE_CLASS_ID_ROADSIGN = 3

# A global OpenCV video capture object used for live video input.
global cap_dict

# To keep track of the previous frame for motion detection for each stream
prev_frame_dict = {}

def load_config(config_path):
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    rtsp_uris = []
    stream_rois = {}

    for index, stream in enumerate(config):
        rtsp_uris.append(stream['uri'])
        # Unpack ROI values from the JSON
        x, y, w, h = stream.get('roi', [0, 0, 1280, 720])
        stream_rois[index] = (x, y, w, h)
        
        print(f"Stream {index} URI: {stream['uri']}")
        print(f"Stream {index} ROI: {x}, {y}, {w}, {h}")

    return rtsp_uris, stream_rois

def motion_detection(frame, roi, stream_index):
    """Detects motion in a given frame using a specified ROI."""
    global prev_frame_dict

    # Extract ROI for motion detection
    x, y, w, h = roi
    roi_frame = frame[y:y+h, x:x+w]
    
    # Convert to grayscale
    gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)

    # Initialize previous frame if not exists
    if stream_index not in prev_frame_dict:
        prev_frame_dict[stream_index] = gray
        return False

    # Compute frame difference
    frame_diff = cv2.absdiff(prev_frame_dict[stream_index], gray)
    _, thresh = cv2.threshold(frame_diff, 25, 255, cv2.THRESH_BINARY)

    # Find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Check if significant motion is detected
    motion_detected = any(cv2.contourArea(c) > 500 for c in contours)

    # Update the previous frame for the next comparison
    prev_frame_dict[stream_index] = gray

    return motion_detected

def cb_need_data(appsource, _size, stream_index):
    global cap_dict, STREAM_ROIS
    ret, frame = cap_dict[stream_index].read()
    if not ret:
        appsource.emit("end-of-stream")
        return

    # Get ROI for the current stream
    ROI_X, ROI_Y, ROI_W, ROI_H = STREAM_ROIS[stream_index]

    # Perform motion detection
    motion_detected = motion_detection(frame, STREAM_ROIS[stream_index], stream_index)

    # Visualize ROI and motion status
    color = (0, 0, 255) if motion_detected else (0, 255, 0)  # Red if motion detected
    cv2.rectangle(frame, (ROI_X, ROI_Y), (ROI_X + ROI_W, ROI_Y + ROI_H), color, 2)

    # Convert frame to RGBA for GStreamer
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)

    # Push the frame into the GStreamer pipeline
    appsource.emit("push-buffer", Gst.Buffer.new_wrapped(frame.tobytes()))

def create_pipeline(uri, pipeline_name, stream_index):
    # Create the individual pipeline for each stream
    pipeline = Gst.Pipeline.new(pipeline_name)

    # Create elements for each stream
    streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
    nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "nvvideo-converter")
    nvosd = Gst.ElementFactory.make("nvdsosd", "on-screen-display")
    sink = Gst.ElementFactory.make("nveglglessink", "egl-overlay")

    if not all([streammux, pgie, nvvidconv, nvosd, sink]):
        sys.stderr.write(" Unable to create one or more elements for the individual pipeline \n")
        sys.exit(1)

    pipeline.add(streammux)
    pipeline.add(pgie)
    pipeline.add(nvvidconv)
    pipeline.add(nvosd)
    pipeline.add(sink)

    # Set properties for the elements
    streammux.set_property('width', 1280)
    streammux.set_property('height', 720)
    streammux.set_property('batch-size', 1)
    streammux.set_property('batched-push-timeout', 15000)

    # Create source element for RTSP stream
    source = Gst.ElementFactory.make("uridecodebin", f"source-{stream_index}")
    if not source:
        sys.stderr.write(f" Unable to create source {stream_index} \n")
        sys.exit(1)

    source.set_property('uri', uri)
    pipeline.add(source)

    # Link source to streammux
    padname = f"sink_0"
    sinkpad = streammux.get_request_pad(padname)
    if not sinkpad:
        sys.stderr.write(f" Unable to get sink pad {padname} \n")
        sys.exit(1)

    def on_pad_added(src, pad, sinkpad):
        print(f"Linking source {src.name} to streammux")
        pad.link(sinkpad)

    source.connect("pad-added", on_pad_added, sinkpad)

    # Configure inference
    pgie.set_property('config-file-path', "opencv/dstest1_pgie_config.txt")

    # Link pipeline elements
    streammux.link(pgie)
    pgie.link(nvvidconv)
    nvvidconv.link(nvosd)
    nvosd.link(sink)

    return pipeline

def main(args):
    # Directly set the path of the JSON config file here
    config_file = "opencv/rtsp.json"

    # Load RTSP URIs and ROIs from the config file
    global cap_dict
    rtsp_uris, STREAM_ROIS = load_config(config_file)

    # Initialize OpenCV VideoCapture for each stream
    cap_dict = {}
    for index, uri in enumerate(rtsp_uris):
        cap_dict[index] = cv2.VideoCapture(uri)
        if not cap_dict[index].isOpened():
            print(f"Failed to open stream {index}: {uri}")
            sys.exit(1)

    # Initialize GStreamer
    GObject.threads_init()
    Gst.init(None)

    print("Creating Pipelines for each stream\n")
    pipelines = []

    # Create an individual pipeline for each stream
    for index, uri in enumerate(rtsp_uris):
        pipeline_name = f"pipeline-{index}"
        pipeline = create_pipeline(uri, pipeline_name, index)
        pipelines.append(pipeline)

    # Start the pipelines
    for pipeline in pipelines:
        pipeline.set_state(Gst.State.PLAYING)

    # Create main loop to handle events
    loop = GObject.MainLoop()
    try:
        loop.run()
    except Exception as e:
        print(f"Pipeline encountered an error: {e}")

    print("Exiting pipeline\n")
    for pipeline in pipelines:
        pipeline.set_state(Gst.State.NULL)

if __name__ == '__main__':
    sys.exit(main(sys.argv))
