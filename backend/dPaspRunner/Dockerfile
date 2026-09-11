FROM ubuntu:jammy AS base

WORKDIR /app

# `apt-get` rather than `apt`: apt prints "WARNING: apt does not have a stable
# CLI interface. Use with caution in scripts." on every invocation. apt-get is
# the scriptable interface and takes the same arguments here.
#
# DEBIAN_FRONTEND stops debconf from printing "unable to initialize frontend"
# and "delaying package configuration" during install.
ENV DEBIAN_FRONTEND=noninteractive

# Quiet pip's root-user warning and self-upgrade check; neither is actionable
# from inside the image.
ENV PIP_ROOT_USER_ACTION=ignore \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

# Ubuntu jammy ships Python 3.10 as its default `python3`, so no PPA is needed
# for the interpreter. This replaces `ppa:deadsnakes/ppa` plus the
# software-properties-common / python3-launchpadlib / add-apt-repository
# machinery it required.
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 \
      python3-dev \
      python3-pip \
    && rm -rf /var/lib/apt/lists/*

# A current pip, so that modern manylinux wheel tags resolve.
RUN python3 -m pip install --no-cache-dir --upgrade pip

# --------------------------------------------------------------------------
FROM base AS mock

COPY requirements.txt ./
RUN python3 -m pip install --no-cache-dir -r requirements.txt

RUN mkdir /blobs

COPY . .

ENV MOCK=y

CMD [ "uvicorn", "--host", "0.0.0.0", "--port", "80", "main:app" ]

# --------------------------------------------------------------------------
FROM base AS dpasp

# dPASP compiles C extensions against clingo, and clingo is NOT installed from
# apt here.
#
# `ppa:potassco/stable` publishes clingo for amd64 and i386 only — there is no
# arm64 build (checked against the Launchpad API). On Apple Silicon the
# repository is added successfully and then `apt-get install clingo` fails
# with "Package 'clingo' has no installation candidate", because no candidate
# exists for the architecture. Ubuntu's own universe clingo is too old for
# dPASP.
#
# The clingo wheel on PyPI solves both problems: it ships `clingo.h` and a
# shared object that exports the full clingo C API, and it publishes aarch64
# wheels. So clingo arrives as a Python package and is then presented to the
# compiler as an ordinary library. No apt repository is involved.
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      libncurses-dev \
    && rm -rf /var/lib/apt/lists/*

# Pinned: this is the C API dPASP's extensions are compiled against, so it
# should not change underneath them without a deliberate bump.
RUN python3 -m pip install --no-cache-dir clingo==5.8.2

# Present the wheel's header and shared object through a conventional
# -I/-l layout. Both filenames embed the Python version and the architecture
# (`_clingo.cpython-310-aarch64-linux-gnu.so`), so they are discovered at
# build time rather than hardcoded.
RUN CLINGO_DIR="$(python3 -c 'import clingo, os; print(os.path.dirname(clingo.__file__))')" && \
    mkdir -p /opt/clingo/include /opt/clingo/lib && \
    ln -s "$CLINGO_DIR/clingo.h"  /opt/clingo/include/clingo.h && \
    ln -s "$CLINGO_DIR/clingo.hh" /opt/clingo/include/clingo.hh && \
    ln -s "$CLINGO_DIR"/_clingo*.so /opt/clingo/lib/libclingo.so && \
    printf '%s\n' "$CLINGO_DIR" > /opt/clingo/dir

# Needed for neural rules and for learning. Kept as its own layer because it
# is by far the largest download in this image.
#
# CPU-only, deliberately. On x86_64 the default PyPI wheel is the CUDA build:
# it carries libtorch_cuda.so (~500 MB) and libc10_cuda.so, and pulls several
# GB of nvidia-* wheels besides. None of it can be used here — runner
# containers are created without `--gpus`, so `torch.cuda.is_available()` is
# False whatever is installed. Measured: 5.3 GB installed with CUDA.
#
# It was not only waste. Importing the CUDA build holds ~790 MB of data
# mappings, which collided with the runner's heap rlimit and failed while
# loading, with
#
#     libc10_cuda.so: failed to map segment from shared object
#
# The arm64 wheel has no CUDA libraries at all, which is why that was only
# ever seen on x86_64 hosts. (`runner_worker.apply_memory_limit` now applies
# the rlimit after the imports, so the collision cannot recur either way.)
#
# If this index has no wheel for the build platform, fall back to PyPI, which
# is what was installed before; the runner works with either.
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
RUN python3 -m pip install --no-cache-dir --index-url "$TORCH_INDEX" torch \
 || { echo "No torch at $TORCH_INDEX for this platform; falling back to PyPI." >&2; \
      python3 -m pip install --no-cache-dir torch; }

# The runpath is the clingo package directory. Linking against the symlink
# makes the linker record the wheel's real shared-object name as the
# dependency, and that directory is where it lives — so the two always agree,
# whatever the architecture or Python version.
RUN CLINGO_DIR="$(cat /opt/clingo/dir)" && \
    CFLAGS="-I/opt/clingo/include" \
    LDFLAGS="-L/opt/clingo/lib -Wl,-rpath,$CLINGO_DIR" \
    python3 -m pip install --no-cache-dir pasp-plp

# Fail the build here, loudly, rather than at a user's first query: check that
# the compiled extension loads, that it can reach clingo through the runpath,
# and that inference returns the right answer.
#
# It also reports which torch build landed and what importing dPASP costs in
# data mappings — the figure the runner's heap budget is added to. A `cuda
# build: 13.0` line here means the fallback above was taken.
RUN python3 -c "import pasp; P = pasp.parse('0.5::a. #query(a)', from_str=True); P.directives['psemantics'] = {'psemantics': 'maxent'}; r = P(quiet=True, status=False); assert abs(r[0][0] - 0.5) < 1e-9, r; print('dPASP self-check passed:', r.tolist())" && \
    python3 -c "import pasp, torch; print('torch', torch.__version__, '| cuda build:', torch.version.cuda); print([l.strip() for l in open('/proc/self/status') if l.startswith('VmData')])"

COPY requirements.txt ./
RUN python3 -m pip install --no-cache-dir -r requirements.txt

RUN mkdir /blobs

COPY . .

ENV MOCK=n

CMD [ "uvicorn", "--host", "0.0.0.0", "--port", "80", "main:app" ]
