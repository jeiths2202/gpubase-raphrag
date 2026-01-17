FROM nvidia/cuda:12.4.0-runtime-ubuntu22.04

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies and Python 3.11
RUN apt-get update && apt-get install -y     software-properties-common     && add-apt-repository ppa:deadsnakes/ppa -y     && apt-get update && apt-get install -y     python3.11     python3.11-venv     python3.11-dev     python3-pip     openssh-server     git     curl     wget     vim     sudo     build-essential     nodejs     npm     && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Configure SSH
RUN mkdir /var/run/sshd
RUN echo 'root:kmsadmin123' | chpasswd
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

# Create kms user
RUN useradd -m -s /bin/bash kmsuser &&     echo 'kmsuser:kmsuser123' | chpasswd &&     usermod -aG sudo kmsuser

# Set working directory
WORKDIR /opt/kms

# Copy source code
COPY . /opt/kms/

# Create virtual environment and install dependencies
RUN python3.11 -m venv /opt/kms/venv
RUN /opt/kms/venv/bin/pip install --upgrade pip
RUN /opt/kms/venv/bin/pip install -r /opt/kms/requirements-api.txt || true

# Set environment
ENV PATH="/opt/kms/venv/bin:$PATH"
ENV CUDA_VISIBLE_DEVICES=4,5,6,7

# Expose ports
EXPOSE 22 3000 9000

# Start SSH daemon
CMD ["/usr/sbin/sshd", "-D"]
