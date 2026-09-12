# Installation

<!-- markdownlint-disable MD046 -->

## Requirements

| Requirement | Version | Needed for |
| --- | --- | --- |
| Python | 3.11 or newer | Every command |
| FFmpeg executable | A build with the required input codecs and H.264 encoder | Event-mode extraction and integration tests |
| Ultralytics and PyTorch | Versions selected by `.[detect]` | Optional object classification |

The base package installs PyAV, NumPy, and headless OpenCV. PyAV handles inspection and
scanning without a standalone `ffmpeg` executable. Source-mode extraction also works without
it because that mode copies files.

## Install from PyPI

Install the released package into an isolated environment.

=== "Windows"

    ```powershell
    py -3.12 -m venv .venv
    .venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    python -m pip install camreview
    ```

=== "macOS / Linux"

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install camreview
    ```

CamReview has no standalone binary or container image.

## Install from source

Clone the repository and use an editable install when developing or testing an unreleased
revision:

```bash
git clone https://github.com/willtheorangeguy/camera-review.git
cd camera-review
python -m pip install -e .
```

## Install FFmpeg

Install FFmpeg only on systems that create event-sized clips or run integration tests.

=== "Windows"

    Install a current FFmpeg build using your package manager, then make its `bin` directory
    available on `PATH`.

    ```powershell
    ffmpeg -version
    ```

=== "Debian / Ubuntu"

    ```bash
    sudo apt update
    sudo apt install -y ffmpeg
    ffmpeg -version
    ```

Accurate event extraction invokes the `libx264` encoder. Confirm that the selected FFmpeg
build includes it when accurate extraction fails.

## Install object classification

Install the detection dependency group on the machine that runs YOLO:

```bash
python -m pip install "camreview[detect]"
```

The base install doesn't import PyTorch or initialize CUDA. For NVIDIA acceleration, install
a PyTorch build compatible with the host driver and CUDA environment, then check it:

```bash
python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

`--device auto` selects `cuda:0` when PyTorch reports CUDA availability and otherwise selects
CPU. An explicit unavailable CUDA device fails with exit code `5`. See
[Configuration](configuration.md#model-storage) before an offline
run because an uncached bare model name may trigger a download.

## Install development tools

The development group adds pytest, pytest-cov, Ruff, and mypy:

```bash
python -m pip install -e ".[dev]"
```

Read [Testing](testing.md) for test selection and [Development guide](development.md) for
the static checks. The base development environment has a documented mypy limitation around
optional detection imports.

## Verify the installation

Run the console entry point from the activated environment:

```bash
camreview --version
```

```text
CamReview 1.0.1
```

If the scripts directory isn't on `PATH`, the module entry point provides the same CLI:

```bash
python -m camreview --version
```

## Upgrade

Upgrade a PyPI installation with:

```bash
python -m pip install --upgrade camreview
```

For an editable source installation, pull the desired revision and reinstall with
`python -m pip install --upgrade -e .`. Install `.[detect]` or `.[dev]` again when that
environment uses the corresponding extra.

## Uninstall

Remove the package from the active environment:

```bash
python -m pip uninstall camreview
```

Deleting the virtual environment removes its remaining dependencies. Model weights live
outside the environment in the cache described under [Configuration](configuration.md), so
remove that directory separately when you no longer need the models.
