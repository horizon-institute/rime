# Running under Windows

At the moment, to work on RIME under Windows, you'll probably want to use the Windows Subsystem for Linux (WSL). 
This gives you a Linux environment within your Windows world, which is closer to the environment RIME was developed in.

If you don't already have WSL installed, you can follow the instructions here:
https://learn.microsoft.com/en-us/windows/wsl/install

This will give you an Ubuntu Linux environment, and you can get a terminal by searching for "Ubuntu" in the Windows command prompt.

Within the Linux world, you'll need to install various tools to get started, so you'll want to run something like the following:

    sudo apt update
    sudo apt install python3 python3-pip python3-dev git-lfs curl 

You'll also need a recent version of node.js, and there are instructions here:
https://learn.microsoft.com/en-us/windows/dev-environment/javascript/nodejs-on-wsl

Essentially, it involves getting the node version manage `nvm` and then using that to install the latest version of node. e.g.

curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/master/install.sh | bash
nvm install 18

If you want to get to your normal Windows home directory, you can find it under `/mnt/c/Users/<your username>`.

Within that directory, you can clone the RIME repository:

    git clone https://github.com/horizon-institute/rime

And within that 'rime' directory you can probably then use the 'run_dev.sh' script as described in the main README.md file.

## Creating a Windows distribution
The Windows release depends on a pre-built Python embedded installation (the `WINDOWS_PYTHON_DIST` variable in `make_release.py`), which must have all Rime's requirements installed.

If you don't have one of these, you can create one by following these steps (assuming that RIME is mounted as z:\rime):

1) With a "fully-fledged" Windows Python installation, run:

    python -m pip wheel -r z:\rime\requirements.txt -w wheels

This builds all the wheels. You will need a compiler installed.

2) Download the Python embedded distribution from python.org and unzip it somewhere.
3) Edit the .pth file to include site-packages (as explained in the file)
4) Install pip by downloading get-pip.py and running it with the embedded Python.
5) Run:

    python -m pip install --no-index --find-links z:\rime\wheels -r z:\rime\requirements.txt

This installs all the wheels. (If you get errors about "invalid signature" here, move the wheels to a local drive.)

6) Zip up the result. You now have an embedded Python installation with all Rime's requirements installed.

If requirements.txt changes, or you're starting from scratch without a wheel dir, you'll need to rebuild all the
wheels. Run:

    python -m pip wheel -w z:\rime\wheels -r z:\rime\requirements.txt

