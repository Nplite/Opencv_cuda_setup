#!/usr/bin/env python3

import sys
sys.path.append('../')
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst
from common.bus_call import bus_call
import os
from os import path
import cv2
import numpy as np
import pyds
import json
import math

MAX_DISPLAY_LEN = 64
MUXER_OUTPUT_WIDTH = 1280
MUXER_OUTPUT_HEIGHT = 720
MUXER_BATCH_TIMEOUT_USEC = 33000
TILED_OUTPUT_WIDTH = 1280
TILED_OUTPUT_HEIGHT = 720
GST_CAPS_FEATURES_NVMM = "memory:NVMM"

# Dictionary to store previous frames and ROIs for motion detection
prev_frames = {}
stream_configs = {}

def load_config(config_file):
    """
    Load stream configurations from JSON file
    """
    try:
        with open(config_file, 'r') as f:
            configs = json.load(f)
        return configs
    except Exception as e:
        sys.stderr.write(f"Error reading config file: {str(e)}\n")
        sys.exit(1)

def detect_motion(frame, stream_id):
    """
    Detect motion in specified ROI using frame differencing method
    """
    global prev_frames, stream_configs
    
    # Get ROI for this stream
    roi = stream_configs[stream_id]['roi']
    x, y, w, h = roi
    
    # Extract ROI from frame
    roi_frame = frame[y:y+h, x:x+w]
    
    # Convert ROI to grayscale
    gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)
    
    # Store first frame
    if stream_id not in prev_frames:
        prev_frames[stream_id] = gray
        return frame, False
    
    # Compute difference between current and previous frame
    frame_delta = cv2.absdiff(prev_frames[stream_id], gray)
    thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
    thresh = cv2.dilate(thresh, None, iterations=2)
    
    # Find contours
    contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    motion_detected = False
    # Draw ROI rectangle
    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
    
    # Draw rectangles around motion areas
    for contour in contours:
        if cv2.contourArea(contour) < 500:  # Filter small movements
            continue
            
        motion_detected = True
        (cx, cy, cw, ch) = cv2.boundingRect(contour)
        # Adjust contour coordinates to full frame coordinates
        cv2.rectangle(frame, 
                     (x + cx, y + cy), 
                     (x + cx + cw, y + cy + ch), 
                     (0, 0, 255), 2)
    
    # Update previous frame
    prev_frames[stream_id] = gray
    
    return frame, motion_detected

def motion_queue_src_pad_buffer_probe(pad, info, u_data):
    frame_number = 0
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return

    # Retrieve batch metadata from the gst_buffer
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    
    while l_frame is not None:
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break

        frame_number = frame_meta.frame_num
        num_surfaces = frame_meta.num_surfaces
        l_surface = frame_meta.surface_list

        while l_surface is not None:
            try:
                surface = pyds.NvDsSurfaceMeta.cast(l_surface.data)
            except StopIteration:
                break

            # Get frame data
            n_frame = surface.surfaceList[0].mappedAddr.data
            frame = np.array(n_frame, copy=True, order='C')
            frame = frame.reshape(frame_meta.height, frame_meta.width, 3)
            
            # Perform motion detection
            processed_frame, motion_detected = detect_motion(frame, frame_meta.pad_index)
            
            if motion_detected:
                # Save frame if motion is detected
                img_path = "{}/stream_{}/frame_{}.jpg".format(folder_name, 
                                                            frame_meta.pad_index, 
                                                            frame_number)
                cv2.imwrite(img_path, processed_frame)
                print(f"Motion detected in stream {frame_meta.pad_index}, frame {frame_number}")

            try:
                l_surface = l_surface.next
            except StopIteration:
                break

        try:
            l_frame = l_frame.next
        except StopIteration:
            break

    return Gst.PadProbeReturn.OK

def cb_newpad(decodebin, decoder_src_pad, data):
    print("In cb_newpad\n")
    caps = decoder_src_pad.get_current_caps()
    gststruct = caps.get_structure(0)
    gstname = gststruct.get_name()
    source_bin = data
    features = caps.get_features(0)

    print("gstname=", gstname)
    if gstname.find("video") != -1:
        print("features=", features)
        if features.contains("memory:NVMM"):
            bin_ghost_pad = source_bin.get_static_pad("src")
            if not bin_ghost_pad.set_target(decoder_src_pad):
                sys.stderr.write("Failed to link decoder src pad to source bin ghost pad\n")
        else:
            sys.stderr.write(" Error: Decodebin did not pick nvidia decoder plugin.\n")

def decodebin_child_added(child_proxy, Object, name, user_data):
    print("Decodebin child added:", name, "\n")
    if name.find("decodebin") != -1:
        Object.connect("child-added", decodebin_child_added, user_data)
    
    if "source" in name:
        source_element = child_proxy.get_by_name("source")
        if source_element.find_property('drop-on-latency') != None:
            Object.set_property("drop-on-latency", True)

def create_source_bin(index, uri):
    print("Creating source bin")

    bin_name = "source-bin-%02d" % index
    print(bin_name)
    nbin = Gst.Bin.new(bin_name)
    if not nbin:
        sys.stderr.write(" Unable to create source bin \n")

    uri_decode_bin = Gst.ElementFactory.make("uridecodebin", "uri-decode-bin")
    if not uri_decode_bin:
        sys.stderr.write(" Unable to create uri decode bin \n")
    uri_decode_bin.set_property("uri", uri)
    uri_decode_bin.connect("pad-added", cb_newpad, nbin)
    uri_decode_bin.connect("child-added", decodebin_child_added, nbin)

    Gst.Bin.add(nbin, uri_decode_bin)
    bin_pad = nbin.add_pad(Gst.GhostPad.new_no_target("src", Gst.PadDirection.SRC))
    if not bin_pad:
        sys.stderr.write(" Failed to add ghost pad in source bin \n")
        return None
    return nbin

def main(args):
    if len(args) != 3:
        sys.stderr.write("usage: %s <config_file.json> <output_folder>\n" % args[0])
        sys.exit(1)

    config_file = args[1]
    global folder_name, stream_configs
    folder_name = args[2]
    
    if path.exists(folder_name):
        sys.stderr.write("The output folder %s already exists. Please remove it first.\n" % folder_name)
        sys.exit(1)

    # Load stream configurations
    configs = load_config(config_file)
    number_sources = len(configs)
    
    # Store configs globally for use in motion detection
    for i, config in enumerate(configs):
        stream_configs[i] = config

    os.mkdir(folder_name)
    
    # Standard GStreamer initialization
    Gst.init(None)
    
    # Create Pipeline element
    print("Creating Pipeline \n ")
    pipeline = Gst.Pipeline()
    is_live = False

    if not pipeline:
        sys.stderr.write(" Unable to create Pipeline \n")
    
    print("Creating streamux \n ")
    streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    if not streammux:
        sys.stderr.write(" Unable to create NvStreamMux \n")

    pipeline.add(streammux)
    
    # Create source bins for each stream
    for i, config in enumerate(configs):
        os.mkdir(folder_name + "/stream_" + str(i))
        print("Creating source_bin ", i, " \n ")
        uri_name = config['uri']
        if uri_name.find("rtsp://") == 0:
            is_live = True
        source_bin = create_source_bin(i, uri_name)
        if not source_bin:
            sys.stderr.write("Unable to create source bin \n")
        pipeline.add(source_bin)
        padname = "sink_%u" % i
        sinkpad = streammux.request_pad_simple(padname)
        if not sinkpad:
            sys.stderr.write("Unable to create sink pad bin \n")
        srcpad = source_bin.get_static_pad("src")
        if not srcpad:
            sys.stderr.write("Unable to create src pad bin \n")
        srcpad.link(sinkpad)

    # Create and add remaining elements
    queue1 = Gst.ElementFactory.make("queue", "queue1")
    queue2 = Gst.ElementFactory.make("queue", "queue2")
    queue3 = Gst.ElementFactory.make("queue", "queue3")
    queue4 = Gst.ElementFactory.make("queue", "queue4")
    queue5 = Gst.ElementFactory.make("queue", "queue5")
    
    tiler = Gst.ElementFactory.make("nvmultistreamtiler", "nvtiler")
    nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "convertor")
    nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")
    
    if not all([queue1, queue2, queue3, queue4, queue5, tiler, nvvidconv, nvosd]):
        sys.stderr.write(" Unable to create one or more elements \n")
        sys.exit(1)

    # Add elements to pipeline
    for element in [queue1, queue2, queue3, queue4, queue5, tiler, nvvidconv, nvosd]:
        pipeline.add(element)

    # Configure stream mux
    streammux.set_property('width', 1920)
    streammux.set_property('height', 1080)
    streammux.set_property('batch-size', number_sources)
    streammux.set_property('batched-push-timeout', MUXER_BATCH_TIMEOUT_USEC)
    streammux.set_property('sync-inputs', 1)

    # Configure tiler
    tiler_rows = int(math.sqrt(number_sources))
    tiler_columns = int(math.ceil((1.0 * number_sources)/tiler_rows))
    tiler.set_property("rows", tiler_rows)
    tiler.set_property("columns", tiler_columns)
    tiler.set_property("width", TILED_OUTPUT_WIDTH)
    tiler.set_property("height", TILED_OUTPUT_HEIGHT)

    # Link elements
    print("Linking elements in the Pipeline \n")
    streammux.link(queue1)
    queue1.link(tiler)
    tiler.link(queue2)
    queue2.link(nvvidconv)
    nvvidconv.link(queue3)
    queue3.link(nvosd)

    # Add probe to the queue2 src pad
    queue2_src_pad = queue2.get_static_pad("src")
    if not queue2_src_pad:
        sys.stderr.write(" Unable to get queue2 src pad \n")
    else:
        queue2_src_pad.add_probe(Gst.PadProbeType.BUFFER, 
                                motion_queue_src_pad_buffer_probe, 0)

    # Create and link sink
    if is_live:
        print("Detected live source, adding video sink \n")
        sink = Gst.ElementFactory.make("nveglglessink", "nvvideo-renderer")
    else:
        print("Creating EGL sink \n")
        sink = Gst.ElementFactory.make("nveglglessink", "nvvideo-renderer")

    if not sink:
        sys.stderr.write(" Unable to create sink element \n")
        sys.exit(1)

    sink.set_property("sync", 0)
    pipeline.add(sink)
    nvosd.link(sink)

    # create an event loop and feed gstreamer bus messages to it
    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", bus_call, loop)

    # List the sources
    print("Now playing...")
    for i, config in enumerate(configs):
        print(i, ": ", config['uri'])
        print(f"ROI: {config['roi']}")

    print("Starting pipeline \n")
    # start play back and listen to events
    pipeline.set_state(Gst.State.PLAYING)
    try:
        loop.run()
    except:
        pass
    # cleanup
    print("Exiting app\n")
    pipeline.set_state(Gst.State.NULL)

if __name__ == '__main__':
    sys.exit(main(sys.argv))