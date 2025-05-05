import cv2
from ultralytics import YOLO
import torch

params = cv2.cudacodec.VideoReaderInitParams()
params.targetSz = (640, 640)

# Load the YOLO TensorRT model
tensorrt_model = YOLO("yolov8n.engine")

# Initialize the CUDA VideoReader
video_reader = cv2.cudacodec.createVideoReader('186.mp4', params=params)
video_reader.set(cv2.cudacodec.COLOR_FORMAT_BGR)

while True:
    # Read the next frame into GPU memory
    ret, gpu_frame = video_reader.nextFrame()
    if not ret:
        break
    
    frame = gpu_frame.download()

    # Perform inference on the frame using YOLO (TensorRT model is GPU-optimized)
    results = tensorrt_model.predict(source=frame, device=0)  # device=0 for GPU inference

    # Process the results (e.g., draw boxes, labels, etc.)
    frame_with_predictions = results[0].plot()  # Get frame with predictions drawn

    cv2.imshow('Frame', frame_with_predictions)

    # Break on pressing 'q'
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release resources
cv2.destroyAllWindows()