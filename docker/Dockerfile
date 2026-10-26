# DF 53.16 + DFHack 53.16-r2 headless, x86_64 (runs under Rosetta/QEMU on Apple Silicon).
# Build:  docker buildx build --platform linux/amd64 \
#           --build-context dl=<dir with the two tarballs> --build-context harness=<repo root> \
#           -f docker/Dockerfile -t yukon-df:53.16 docker
FROM --platform=linux/amd64 debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      bzip2 ca-certificates procps python3 locales \
      libsdl2-2.0-0 libsdl2-image-2.0-0 libsdl2-mixer-2.0-0 libsdl2-ttf-2.0-0 \
      libncursesw6 libglu1-mesa libgl1 libopenal1 zlib1g \
    && sed -i "s/^# en_US.UTF-8/en_US.UTF-8/" /etc/locale.gen && locale-gen && rm -rf /var/lib/apt/lists/*
ENV HOME=/root LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 TERM=xterm
WORKDIR /root/dfprobe
COPY --from=dl df_53_16_linux.tar.bz2 dfhack-53.16-r2-Linux-64bit.tar.bz2 /tmp/
RUN mkdir df && tar xjf /tmp/df_53_16_linux.tar.bz2 -C df && tar xjf /tmp/dfhack-53.16-r2-Linux-64bit.tar.bz2 -C df \
    && rm /tmp/*.tar.bz2
# repo df/prefs + df/dfhack-config overlay the stock install (COPY merges directories)
COPY --from=harness . /root/dfprobe/
# init.txt / d_init.txt = stock defaults + four token edits (the public export ships only the edits)
RUN rm -rf .git && python3 docker/prefs_overrides.py df
COPY start_df.sh /root/dfprobe/start_df.sh
# DFHack's overlay plugin off once a fort loads: saves ~0.7 core per paused DF (dfhack-onMapLoad.init, runs/m5-df-speed-2026-10-22)
COPY dfhack-onMapLoad.init /root/dfprobe/df/dfhack-config/init/onMapLoad.init
RUN chmod +x *.sh df/dfhack df/dfhack-run && (ldd df/dwarfort | grep 'not found' || echo 'all libs resolved')
CMD ["sleep", "infinity"]
