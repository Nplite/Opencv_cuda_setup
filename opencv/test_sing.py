import sys
import gi
import cv2
from common.bus_call import bus_call

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
global cap

# Define the ROI for motion detection (e.g., center of the frame)
ROI_X, ROI_Y, ROI_W, ROI_H = 300, 250, 500, 400  # Define ROI dimensions (x, y, width, height)

# To keep track of the previous frame for motion detection
prev_frame = None

def motion_detection(frame):
    '''
    Detects motion within the defined ROI using frame differencing.
    '''
    global prev_frame

    # Convert the frame to grayscale for motion detection
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Crop the region of interest (ROI)
    roi_gray = gray[ROI_Y:ROI_Y + ROI_H, ROI_X:ROI_X + ROI_W]

    # Initialize the previous frame if it doesn't exist
    if prev_frame is None:
        prev_frame = roi_gray
        return False  # No motion detected initially

    # Compute the absolute difference between the current and previous frame
    frame_diff = cv2.absdiff(prev_frame, roi_gray)
    _, thresh = cv2.threshold(frame_diff, 25, 255, cv2.THRESH_BINARY)

    # Find contours of the moving objects within the threshold
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # If contours are detected, it means there is motion
    motion_detected = False
    for contour in contours:
        if cv2.contourArea(contour) > 500:  # Minimum area for motion to be considered (adjustable)
            motion_detected = True
            break

    # Update previous frame for the next iteration
    prev_frame = roi_gray

    return motion_detected


def cb_need_data(appsource, _size, u_data):
    '''
    Callback invoked when GStreamer requests new data.
    Captures a frame from the live video stream (cap.read()).
    Converts the frame from BGR to RGBA using OpenCV.
    Pushes the frame into the GStreamer pipeline using appsource.emit("push-buffer").
    '''
    global cap
    ret, frame = cap.read()
    if not ret:
        appsource.emit("end-of-stream")
        return

    # Draw the ROI rectangle on the frame
    cv2.rectangle(frame, (ROI_X, ROI_Y), (ROI_X + ROI_W, ROI_Y + ROI_H), (0, 255, 0), 2)  # Green color, 2 px thickness

    # Perform motion detection in the ROI
    if motion_detection(frame):
        print("Motion detected in the ROI!")

    # Convert frame from BGR to RGBA
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
    
    # Push the frame into the GStreamer pipeline
    appsource.emit("push-buffer", Gst.Buffer.new_wrapped(frame.tobytes()))


def osd_sink_pad_buffer_probe(pad, info, u_data):
    '''
    Purpose: Extracts metadata (e.g., frame numbers, detected objects) from the inference pipeline.
    pyds.gst_buffer_get_nvds_batch_meta: Retrieves batch metadata from a GStreamer buffer.
    frame_meta.frame_num: Accesses the frame number of each frame in the batch.
    Gst.PadProbeReturn.OK: Indicates that processing should continue.
    '''
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer")
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

def main(args):

    # Purpose: Ensures the script is called with a valid input (file or URI).
    if len(args) < 2:
        sys.stderr.write("usage: %s <media file or uri>\n" % args[0])
        sys.exit(1)

    global cap
    input_is_file = args[1].endswith(('.mp4', '.avi', '.mkv', '.mov', 'webm'))
    cap = None

    if not input_is_file:
        cap = cv2.VideoCapture(args[1])
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if not cap.isOpened():
            print("Can't open input stream. Exiting ...")
            sys.exit(-1)

    # Initialization: Prepares GStreamer and GObject threading.
    GObject.threads_init()
    Gst.init(None)

    # Pipeline: A container for linking all elements.
    print("Creating Pipeline \n")
    pipeline = Gst.Pipeline()
    if not pipeline:
        sys.stderr.write(" Unable to create Pipeline \n")

    print("Creating elements \n")

    # Source elements
    source = None
    appsource = None
    if input_is_file:
        source = Gst.ElementFactory.make("filesrc", "file-source")
        if not source:
            sys.stderr.write(" Unable to create Source \n")
    else:
        appsource = Gst.ElementFactory.make("appsrc", "opencv-source")
        if not appsource:
            sys.stderr.write(" Unable to create appsrc Source \n")

    h264parser = Gst.ElementFactory.make("h264parse", "h264-parser")
    decoder = Gst.ElementFactory.make("nvv4l2decoder", "nvv4l2-decoder")
    nvvideoconvert = Gst.ElementFactory.make("nvvideoconvert", "nv-videoconv")
    caps_filter = Gst.ElementFactory.make("capsfilter", "capsfilter")
    streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
    nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "nvvideo-converter")
    nvosd = Gst.ElementFactory.make("nvdsosd", "on-screen-display")
    sink = Gst.ElementFactory.make("nveglglessink", "egl-overlay")

    if not (h264parser and decoder and streammux and pgie and nvvidconv and nvosd and sink):
        sys.stderr.write(" Unable to create one or more elements \n")

    # Input Properties
    if input_is_file:
        source.set_property('location', args[1])
    else:
        caps1 = Gst.Caps.from_string("video/x-raw,format=RGBA,width=%d,height=%d,framerate=15/1" % (width, height))
        caps2 = Gst.Caps.from_string("video/x-raw(memory:NVMM),format=NV12,width=%d,height=%d,framerate=15/1" % (width, height))
        appsource.set_property('caps', caps1)
        caps_filter.set_property('caps', caps2)

    streammux.set_property('width', width if not input_is_file else 1280)
    streammux.set_property('height', height if not input_is_file else 720)
    streammux.set_property('batch-size', 1)
    streammux.set_property('batched-push-timeout', 4000000)
    pgie.set_property('config-file-path', "opencv/dstest1_pgie_config.txt")

    # Adding elements to Pipeline
    print("Adding elements to Pipeline \n")
    if input_is_file:
        pipeline.add(source)
    else:
        pipeline.add(appsource)
    pipeline.add(h264parser)
    pipeline.add(decoder)
    pipeline.add(nvvideoconvert)
    pipeline.add(caps_filter)
    pipeline.add(streammux)
    pipeline.add(pgie)
    pipeline.add(nvvidconv)
    pipeline.add(nvosd)
    pipeline.add(sink)

    # Linking elements
    print("Linking elements in the Pipeline \n")
    if input_is_file:
        source.link(h264parser)
        h264parser.link(decoder)
        srcpad = decoder.get_static_pad("src")
    else:
        appsource.link(nvvideoconvert)
        nvvideoconvert.link(caps_filter)
        srcpad = caps_filter.get_static_pad("src")

    # Linking the rest of the pipeline
    sinkpad = streammux.get_request_pad("sink_0")
    if not sinkpad:
        sys.stderr.write(" Unable to get the sink pad of streammux \n")
    if not srcpad:
        sys.stderr.write(" Unable to get source pad \n")
    srcpad.link(sinkpad)

    streammux.link(pgie)
    pgie.link(nvvidconv)
    nvvidconv.link(nvosd)
    nvosd.link(sink)

    # Connecting signals and starting loop
    loop = GObject.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", bus_call, loop)

    if not input_is_file:
        appsource.connect("need-data", cb_need_data, None)

    # Start the pipeline
    print("Starting pipeline\n")
    pipeline.set_state(Gst.State.PLAYING)
    try:
        loop.run()
    except:
        pass

    print("Exiting pipeline\n")
    pipeline.set_state(Gst.State.NULL)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
