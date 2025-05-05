import sys
import gi
import json
import configparser
from datetime import datetime

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GLib, GstRtspServer

class MultiCameraMotionDetector:
    def __init__(self, config_path):
        """
        Initialize Multi-Camera Motion Detection Pipeline
        
        :param config_path: Path to DeepStream configuration
        """
        # Initialize configuration
        self.config = self._parse_config(config_path)
        
        # Initialize GStreamer
        Gst.init(None)
        
        # Create main pipeline
        self.pipeline = Gst.Pipeline.new('multi-camera-motion')
        
        # Create pipeline elements
        self._create_pipeline_elements()
        
        # Configure pipeline elements
        self._configure_pipeline()
        
        # Set up motion detection callbacks
        self._setup_motion_detection()
    
    def _parse_config(self, config_path):
        """
        Parse configuration file
        
        :param config_path: Path to configuration file
        :return: Parsed configuration dictionary
        """
        config = configparser.ConfigParser()
        config.read(config_path)
        return config
    
    def _create_pipeline_elements(self):
        """
        Create GStreamer pipeline elements
        """
        # Stream multiplexer
        self.streammux = Gst.ElementFactory.make('nvstreammux', 'stream-mux')
        if not self.streammux:
            raise RuntimeError("Failed to create streammux")
        
        # Primary inference engine (object detector)
        self.primary_gie = Gst.ElementFactory.make('nvinfer', 'primary-inference')
        if not self.primary_gie:
            raise RuntimeError("Failed to create primary inference engine")
        
        # Tracker
        self.tracker = Gst.ElementFactory.make('nvtracker', 'object-tracker')
        if not self.tracker:
            raise RuntimeError("Failed to create tracker")
        
        # Tiler for displaying multiple streams
        self.tiler = Gst.ElementFactory.make('nvmultistreamtiler', 'tiler')
        if not self.tiler:
            raise RuntimeError("Failed to create tiler")
        
        # Video converter
        self.nvvidconv = Gst.ElementFactory.make('nvvidconv', 'converter')
        if not self.nvvidconv:
            raise RuntimeError("Failed to create video converter")
        
        # On-screen display
        self.nvosd = Gst.ElementFactory.make('nvdsosd', 'onscreen-display')
        if not self.nvosd:
            raise RuntimeError("Failed to create on-screen display")
        
        # Sink (could be display or file)
        self.sink = Gst.ElementFactory.make('filesink', 'file-sink')
        if not self.sink:
            raise RuntimeError("Failed to create sink")
    
    def _configure_pipeline(self):
        """
        Configure pipeline elements based on configuration
        """
        # Configure streammux
        streammux_config = self.config['streammux']
        self.streammux.set_property('gpu-id', int(streammux_config.get('gpu-id', 0)))
        self.streammux.set_property('batch-size', int(streammux_config.get('batch-size', 6)))
        self.streammux.set_property('width', int(streammux_config.get('width', 1280)))
        self.streammux.set_property('height', int(streammux_config.get('height', 760)))
        
        # Configure primary inference
        primary_gie_config = self.config['primary-gie']
        self.primary_gie.set_property('config-file-path', primary_gie_config.get('config-file', ''))
        self.primary_gie.set_property('model-engine-file', primary_gie_config.get('model-engine-file', ''))
        
        # Configure tiler
        tiled_display_config = self.config['tiled-display']
        self.tiler.set_property('width', int(tiled_display_config.get('width', 1920)))
        self.tiler.set_property('height', int(tiled_display_config.get('height', 1080)))
        
        # Configure sink
        self.sink.set_property('location', 'motion_events.log')
    
    def _setup_motion_detection(self):
        """
        Set up motion detection logic and callbacks
        """
        # Add callback for object detection
        self.primary_gie.connect('pad-added', self._on_inference_pad_added)
    
    def _on_inference_pad_added(self, element, pad):
        """
        Callback for processing inference results
        
        :param element: GStreamer element
        :param pad: Pad with inference results
        """
        # Extract motion detection information
        try:
            # Get metadata from the pad
            meta = pad.get_sticky_event('GstInferenceMeta', 0)
            if meta:
                # Process detected objects
                objects = meta.get_objects()
                for obj in objects:
                    # Check if object represents motion
                    if self._is_motion_detected(obj):
                        self._log_motion_event(obj)
        except Exception as e:
            print(f"Motion detection error: {e}")
    
    def _is_motion_detected(self, obj):
        """
        Determine if an object represents motion
        
        :param obj: Detected object
        :return: Boolean indicating motion detection
        """
        # Implement motion detection logic
        # Could use object size, confidence, movement between frames, etc.
        confidence_threshold = 0.5
        return obj.confidence > confidence_threshold
    
    def _log_motion_event(self, obj):
        """
        Log motion detection event
        
        :param obj: Detected motion object
        """
        event = {
            'timestamp': datetime.now().isoformat(),
            'confidence': obj.confidence,
            'class': obj.class_id,
            'bbox': obj.bbox
        }
        
        # Log to file
        with open('motion_events.json', 'a') as f:
            json.dump(event, f)
            f.write('\n')
        
        # Print motion alert
        print(f"MOTION DETECTED: {event}")
        
        # Implement additional notification methods
        self._send_alert(event)
    
    def _send_alert(self, event):
        """
        Send notifications for motion events
        
        :param event: Motion event details
        """
        # Placeholder for alert mechanisms
        # Could implement SMS, email, cloud notifications, etc.
        pass
    
    def start_detection(self):
        """
        Start multi-camera motion detection pipeline
        """
        # Add sources from configuration
        sources = self.config['source-list']['list'].split(';')
        self.sources = []
        
        for idx, url in enumerate(sources):
            # Create URI source bin
            source = Gst.ElementFactory.make('urisourcebin', f'source-{idx}')
            source.set_property('uri', url)
            self.sources.append(source)
            
            # Add to pipeline
            self.pipeline.add(source)
            
            # Link source to streammux
            source.connect('pad-added', self._on_pad_added, idx)
        
        # Add other elements to pipeline
        for element in [self.streammux, self.primary_gie, self.tracker, 
                        self.tiler, self.nvvidconv, self.nvosd, self.sink]:
            self.pipeline.add(element)
        
        # Link pipeline elements
        # (Add appropriate linking logic here)
        
        # Start pipeline
        self.pipeline.set_state(Gst.State.PLAYING)
        
        # Run main loop
        loop = GLib.MainLoop()
        loop.run()
    
    def _on_pad_added(self, src, new_pad, source_idx):
        """
        Dynamically link source pads to streammux
        
        :param src: Source element
        :param new_pad: Newly created pad
        :param source_idx: Index of the source
        """
        sink_pad = self.streammux.get_request_pad(f'sink_{source_idx}')
        new_pad.link(sink_pad)
    
    def stop_detection(self):
        """
        Stop motion detection pipeline
        """
        self.pipeline.set_state(Gst.State.NULL)

def main():
    try:
        config_path = 'test/cv_multi.txt'  # Path to your configuration file
        detector = MultiCameraMotionDetector(config_path)
        detector.start_detection()
    except Exception as e:
        print(f"Motion detection initialization failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()