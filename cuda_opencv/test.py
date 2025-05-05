# import cv2

# video_reader = cv2.cudacodec.createVideoReader('186.mp4')
# while True:
#     ret, gpu_frame = video_reader.nextFrame()
#     if not ret:
#         break
#     # Download frame to host if further CPU processing is needed
#     frame = gpu_frame.download()
#     # Process frame
#     cv2.imshow('Frame', frame)
#     if cv2.waitKey(1) & 0xFF == ord('q'):
#         break
# cv2.destroyAllWindows()


import cv2

# List all attributes of cv2.cudacodec
attributes = dir(cv2)
print("Available attributes and methods in cv2.cudacodec:")
print(attributes)






# import cv2

# # Use help() to get detailed documentation of createVideoWriter
# print(help(cv2.cuda.FarnebackOpticalFlow()
# ))
# import cv2

# help(cv2)