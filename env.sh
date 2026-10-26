export DFP=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
export LD_LIBRARY_PATH=$DFP/sysroot/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export PATH=$DFP/sysroot/usr/bin:$PATH
