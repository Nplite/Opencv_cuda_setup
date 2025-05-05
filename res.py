import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
import time

def on_pad_added(decodebin, pad):
    """
    Callback function that is called when a pad is added to the decodebin.
    It queries the capabilities (caps) of the video stream and extracts useful information.
    """
    try:
        # Query capabilities of the video stream
        caps = pad.query_caps(None)
        structure = caps.get_structure(0)
        
        # Extract video stream properties
        format = structure.get_string("format") if structure.has_field("format") else "Unknown"
        width = structure.get_int("width")[1] if structure.has_field("width") else "Unknown"
        height = structure.get_int("height")[1] if structure.has_field("height") else "Unknown"
        framerate = structure.get_fraction("framerate")[1] if structure.has_field("framerate") else "Unknown"
        
        # Validate and print the extracted information
        if width != "Unknown" and height != "Unknown" and framerate != "Unknown":
            print(f"Format: {format}, Width: {width}, Height: {height}, Framerate: {framerate}")
        else:
            print("Error: Invalid video capabilities detected.")
    
    except Exception as e:
        print(f"Error in on_pad_added: {e}")

def query_video_capabilities(rtsp_url):
    """
    Set up the GStreamer pipeline to access the RTSP stream and query video capabilities.
    """
    try:
        # Initialize GStreamer
        Gst.init(None)

        # Create a pipeline and elements
        pipeline = Gst.parse_launch(f"rtspsrc location={rtsp_url} ! decodebin name=dec")
        
        # Get the decodebin element
        decodebin = pipeline.get_by_name('dec')
        
        # Connect the on_pad_added function to the "pad-added" signal of decodebin
        decodebin.connect("pad-added", on_pad_added)
        
        # Start the pipeline
        pipeline.set_state(Gst.State.PLAYING)
        print("Pipeline set to PLAYING state.")
        
        # Wait for a few seconds to allow pad-added to be triggered
        start_time = time.time()
        while True:
            # Check for errors or warnings in the pipeline
            if pipeline.get_state(0).state == Gst.State.NULL:
                print("Pipeline failed to play.")
                break

            # Wait for 10 seconds before checking again
            time.sleep(1)

            # Stop after 30 seconds if no pad-added is triggered
            if time.time() - start_time > 30:
                print("Timed out waiting for pad-added.")
                break

        # Stop the pipeline after querying
        pipeline.set_state(Gst.State.NULL)
        print("Pipeline set to NULL state.")

    except Exception as e:
        print(f"Error in query_video_capabilities: {e}")


if __name__ == "__main__":
    rtsp_url = "rtsp://ProjectTheft2024:Theft%402024@103.194.88.114/cam/realmonitor?channel=1&subtype=0"  # Replace with your RTSP URL
    query_video_capabilities(rtsp_url)


