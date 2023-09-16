# Developing for PortMaster

The easiest way to develop and test PortMaster is not on the device but your local machine. 

## Setting up the environment

Have Python 3.9 or newer, install [pysdl2-dll](https://pypi.org/project/pysdl2-dll/) for your platform via pip/brew/apt.

Thats it, everything else is included.

## Running PortMaster

PortMaster is the bash script that runs on the device, this is not needed for development. Instead you're better off running the pugwash script directly

```bash
python3 PortMaster/pugwash
```

If you have made changes and want to test it on your device you can use the do_release.sh script, this will zip it up correctly to test it on your device.

```bash
./do_release.sh
```

From there you can just ssh it onto the device and use harbourmaster to install this local version of PortMaster.

```bash
scp PortMaster.zip ark@rg353v.local:/roms2/tools
```

Then on device:

```bash
cd /roms2/tools
./PortMaster/harbourmaster --no-check install ./PortMaster.zip
```

The `./PortMaster.zip` is important as it will make harbourmaster use the local file.


## Tips and Tricks

In PortMaster/pugwash there is a variable called `pretend_device`, you can use that to run the script with the resolution/hardware info of that device. Just uncomment the line for the device you wish to impersonate. This is useful for testing themes too. You will just need to search the file for the variable.

```python
    ## Uncomment one of these to pretend to be a different device. more devices in pylibs/harbourmaster/hardware.py
    pretend_device = (
        # 'rg351p'
        # 'rg552'
        # 'rg503'
        # 'rg351v'
        # 'rg353v'
        # 'ogs'
        # 'ogu'
        # 'x55'
        )
```
