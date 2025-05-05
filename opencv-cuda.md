# OpenCV 4.10.0 with CUDA 12.6.3 Dockerfile

This Dockerfile builds an image based on ```Ubuntu 22.04``` that includes ```OpenCV 4.10.0``` with ```CUDA 12.6.3``` support and integrates the ```Video Codec SDK 12.2.72``` for video encoding/decoding.

## 1. Create the Dockerfile	

Below is the complete Dockerfile content you can copy this content to a file named `Dockerfile`.

```dockerfile 
ARG CUDA="12.6.3"
ARG UBUNTU="22.04"
ARG ARCH=""
FROM nvidia/cuda${ARCH}:${CUDA}-devel-ubuntu${UBUNTU}
ARG NVIDIA_DISTRO="ubuntu2204/x86_64"
ARG OPENCV="4.10.0"
ARG CUDA_ARCH_BIN="8.9"	          # Set CUDA compute capability (adjust as needed)
ARG CUDA_ARCH_PTX=""
ARG CUDNN="OFF"	                  # Set to ON if you want cuDNN support
ARG VIDEO_CODEC_SDK="12.2.72"
ARG VIDEO_CODEC_SDK_PATH="video_codec_sdk"
ENV DEBIAN_FRONTEND=noninteractive
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility,video

# Install required packages
RUN apt update && apt install -y --no-install-recommends build-essential \
    cmake \
    cmake-data \
    gcc g++ \
    gdb \
    git \
    wget \
    unzip \
    yasm \
    doxygen \
    pkg-config \
    checkinstall \
    libatlas-base-dev \
    gfortran \
    libflann-dev \
    libglew-dev \
    libgdal-dev \
    libeigen3-dev \
    libgflags-dev \
    libgoogle-glog-dev \
    libprotobuf-dev \
    protobuf-compiler \
    libgtk2.0-dev \
    python3 python3-dev python3-numpy \
    libleptonica-dev \
    libtesseract-dev \
    liblapack-dev \
    libhdf5-serial-dev \
    qtbase5-dev qtchooser qt5-qmake qtbase5-dev-tools \
    libgtk-3-dev \
    zlib1g-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev libtiff5-dev \
    libdc1394-dev \
    ffmpeg \
    libavcodec-dev libavformat-dev libavutil-dev libswscale-dev \
    libgstreamer1.0-0 libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev \
    gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
    gir1.2-gst-rtsp-server-1.0 gstreamer1.0-rtsp gstreamer1.0-plugins-base-apps \
    libv4l-dev \
    libtbb-dev libtbb2

WORKDIR /tmp

# Copy Video Codec SDK and create symbolic link
ADD ${VIDEO_CODEC_SDK_PATH}/Video_Codec_SDK_${VIDEO_CODEC_SDK}.zip /tmp
RUN unzip Video_Codec_SDK_${VIDEO_CODEC_SDK}.zip && rm Video_Codec_SDK_${VIDEO_CODEC_SDK}.zip

# Install Video Codec SDK headers into CUDA include directory
RUN cp /tmp/Video_Codec_SDK_${VIDEO_CODEC_SDK}/Interface/* /usr/local/cuda/include/

# Copy libraries for the Video Codec SDK and create necessary symbolic links
RUN cp /tmp/Video_Codec_SDK_${VIDEO_CODEC_SDK}/Lib/linux/stubs/x86_64/* /usr/lib/x86_64-linux-gnu/ && \
    ln -s /usr/lib/x86_64-linux-gnu/libnvcuvid.so /usr/lib/x86_64-linux-gnu/libnvcuvid.so.1 && \
    ln -s /usr/lib/x86_64-linux-gnu/libnvidia-encode.so /usr/lib/x86_64-linux-gnu/libnvidia-encode.so.1 && \
    ln -s /usr/lib/x86_64-linux-gnu/libnvcuvid.so.1 /usr/local/cuda/lib64/libnvcuvid.so && \
    ln -s /usr/lib/x86_64-linux-gnu/libnvidia-encode.so.1 /usr/local/cuda/lib64/libnvidia-encode.so
    
    # Cleanup extracted SDK files
    rm -rf /tmp/Video_Codec_SDK_${VIDEO_CODEC_SDK}

# Clone OpenCV and opencv_contrib repositories at version 4.10.0
RUN git clone --branch 4.10.0 https://github.com/opencv/opencv.git
RUN git clone --branch 4.10.0 https://github.com/opencv/opencv_contrib.git

# Build and install OpenCV with CUDA support
RUN mkdir opencv/build && \
    cd opencv/build && \
    cmake -DCMAKE_BUILD_TYPE=RELEASE \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DCMAKE_LIBRARY_PATH=/usr/local/cuda/lib64/stubs \
        -DWITH_CUDA=ON \
        -DWITH_NVCUVID=ON \
        -DWITH_CUDNN=${CUDNN} \
        -DWITH_CUBLAS=ON \
        -DWITH_TBB=ON \
        -DWITH_GTK=ON \
        -DWITH_QT=ON \
        -DENABLE_FAST_MATH=ON \
        -DCUDA_FAST_MATH=ON \
        -DCUDA_ARCH_BIN=${CUDA_ARCH_BIN} \
        -DCUDA_ARCH_PTX=${CUDA_ARCH_PTX} \
        -DOPENCV_EXTRA_MODULES_PATH=/tmp/opencv_contrib/modules \
        -DOPENCV_DNN_CUDA=${CUDNN} \
        -DOPENCV_ENABLE_NONFREE=OFF \
        -DBUILD_TESTS=OFF \
        -DBUILD_PERF_TESTS=OFF \
        -DBUILD_EXAMPLES=OFF \
        -DBUILD_JAVA=OFF \
        -DBUILD_opencv_apps=ON \
        -DBUILD_opencv_python2=OFF \
        -DBUILD_opencv_python3=ON \
        .. && \
    make -j$(nproc) && \
    make install && \
    ldconfig
```
## 2. Setup
Before you build the Docker image, complete the following steps:

**1. Download the Video Codec SDK:**
   - Obtain the `Video_Codec_SDK_12.2.72.zip` file.
   - Create a folder named `video_codec_sdk` in the same directory as your `Dockerfile`.
   - Place the downloaded zip file inside the `video_codec_sdk` folder.

**2. Ensure GPU Drivers Are Installed:**
   - Install NVIDIA drivers and Docker with GPU support (`nvidia-container-toolkit`).


## 3. Build the Docker Image
Open your terminal, navigate to the directory containing your `Dockerfile` and `video_codec_sdk` folder, then run the following command:

```bash 
docker build -t opencv-cuda .
```

## 4. Running the Container

**1. Enable Display Support (if needed)**
   
   If you need GUI applications inside Docker, run:
   ```bash
   xhost +local:docker

   ```

**2  Install dependencies**
```
apt install python3 pip
pip install numpy==1.23.5
pip install ultralytics
pip install cupy-cuda12x
pip install -r requirements.txt
```
**3. Run the Container**

   Use the following command to start a container with GPU access:
   ```bash
docker run --rm -it -p 8888:8888 --gpus all \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v /home/aiserver/Desktop/cuda_opencv:/workspace \
  opencv-cuda

cd ..
cd workspace
   ```
