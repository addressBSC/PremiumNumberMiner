# Deployment & Setup Guide

This guide provides step-by-step instructions on how to set up and run the PremiumNumber Miner.

## Prerequisites
- Python 3.8 or higher
- (Optional) OpenCL drivers for GPU mining
- A BSC wallet with some BNB for gas

## Installation

### 1. Clone the Repository
```bash
git clone https://github.com/addressBSC/PremiumNumberMiner.git
cd PremiumNumberMiner
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Build C Extension (Optional but Recommended)
For CPU mining acceleration:
```bash
python setup.py build_ext --inplace
```

## Configuration
Edit `config.yaml` with your settings:
- `private_key`: Your wallet private key (Required)
- `solver`: Set to `cpu` or `gpu`
- `min_trailing_8s`: Minimum number of trailing '8's required (Default: 9)

## Running the Miner
```bash
python premium_miner.py
```

## Building Windows Executable
If you are on Windows, you can use the provided batch file:
1. Run `build.bat`.
2. Find the executable in the `dist` folder.
