ARG CUDA="12.6.3"
ARG UBUNTU="22.04"
ARG ARCH=""

FROM nvidia/cuda${ARCH}:${CUDA}-devel-ubuntu${UBUNTU}

ARG NVIDIA_DISTRO="ubuntu2204/x86_64"
ARG OPENCV="4.10.0"
ARG CUDA_ARCH_BIN="8.9"
ARG CUDA_ARCH_PTX=""
ARG CUDNN="OFF"
ARG VIDEO_CODEC_SDK="12.2.72"
ARG VIDEO_CODEC_SDK_PATH="Video_Codec_SDK"

ENV DEBIAN_FRONTEND=noninteractive
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility,video

RUN apt update && apt install -y --no-install-recommends build-essential \
    cmake \
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
    python3 python3-dev python3-numpy \
    libleptonica-dev \
    libtesseract-dev \
    liblapack-dev \
    libhdf5-serial-dev \
    libgtk2.0-dev \
    libqt5x11extras5-dev \
    libcanberra-gtk-module \
    # GUI
    qtbase5-dev qtchooser qt5-qmake qtbase5-dev-tools \
    libgtk-3-dev libgtk2.0-dev \
    libvtk9-dev \
    # media io
    zlib1g-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev libtiff5-dev \
    # video i/o
    libdc1394-dev \
    ffmpeg \
    libavcodec-dev libavformat-dev libavutil-dev libswscale-dev \
    libgstreamer1.0-0 libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev \
    gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
    gir1.2-gst-rtsp-server-1.0 gstreamer1.0-rtsp gstreamer1.0-plugins-base-apps \
    libv4l-dev \
    # parallel framework
    libtbb-dev libtbb2

WORKDIR /tmp

# Copy Video Codec SDK and create symbolic link
ADD Video_Codec_SDK_12.2.72.zip /tmp

RUN unzip Video_Codec_SDK_12.2.72.zip && rm Video_Codec_SDK_12.2.72.zip
RUN cp /tmp/Video_Codec_SDK_12.2.72/Interface/* /usr/local/cuda/include/
RUN cp /tmp/Video_Codec_SDK_12.2.72/Lib/linux/stubs/x86_64/* /usr/lib/x86_64-linux-gnu/ && \
    ln -s /usr/lib/x86_64-linux-gnu/libnvcuvid.so /usr/lib/x86_64-linux-gnu/libnvcuvid.so.1 && \
    ln -s /usr/lib/x86_64-linux-gnu/libnvidia-encode.so /usr/lib/x86_64-linux-gnu/libnvidia-encode.so.1 && \
    ln -s /usr/lib/x86_64-linux-gnu/libnvcuvid.so.1 /usr/local/cuda/lib64/libnvcuvid.so && \
    ln -s /usr/lib/x86_64-linux-gnu/libnvidia-encode.so.1 /usr/local/cuda/lib64/libnvidia-encode.so

    # Add these lines before the OpenCV build section
# RUN wget https://developer.download.nvidia.com/compute/redist/cudnn/v8.9.5/cudnn-12.6-linux-x64-v8.9.5.29.tgz && \
#     tar -xzvf cudnn-12.6-linux-x64-v8.9.5.29.tgz && \
#     cp cuda/include/cudnn*.h /usr/local/cuda/include && \
#     cp cuda/lib64/libcudnn* /usr/local/cuda/lib64 && \
#     chmod a+r /usr/local/cuda/include/cudnn*.h /usr/local/cuda/lib64/libcudnn*


RUN git clone --branch 4.10.0 https://github.com/opencv/opencv.git
RUN git clone --branch 4.10.0 https://github.com/opencv/opencv_contrib.git

RUN mkdir opencv/build && \
    cd opencv/build && \
    cmake \
        -DCMAKE_BUILD_TYPE=RELEASE \
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
        -DWITH_FFMPEG=ON \
        .. | tee /tmp/cmake_log.txt && \
    make -j$(nproc) VERBOSE=1 | tee /tmp/make_log.txt && \
    make install && \
    ldconfig