# GitHub Copilot Instructions for PortMaster GUI

## Project Overview
PortMaster is a GUI application for managing game ports on handheld Linux devices. The project is written in Python and uses SDL2 for graphics rendering.

## Development Setup

### Prerequisites
- Python 3.9 or newer
- pysdl2-dll for your platform (via pip/brew/apt)

### Running Locally
```bash
python3 PortMaster/pugwash
```

### Testing Changes on Device
```bash
./do_release.sh
scp PortMaster.zip ark@rg353v.local:/roms2/tools
# Then on device:
cd /roms2/tools
./PortMaster/harbourmaster --no-check install ./PortMaster.zip
```

## Code Structure

### Main Components
- **PortMaster/pugwash**: Main entry point for GUI application
- **PortMaster/pylibs/harbourmaster/**: Core library modules
  - `harbour.py`: Main HarbourMaster class for port management
  - `hardware.py`: Hardware detection and device profiles
  - `platform.py`: Platform-specific functionality
  - `source.py`: Port source management
  - `util.py`: Utility functions
  - `config.py`: Configuration management
  - `info.py`: Port information handling
  - `captain.py`: Captain functionality

### Key Design Patterns
- The codebase uses callback-based architecture for UI updates
- Port information is cached and loaded from JSON files
- File signatures are used to track renamed files

## Development Guidelines

### Code Style
- Follow existing code style in the repository
- Use `.flake8` configuration for linting
- Preserve existing comment styles

### Testing
- Use Python's built-in unittest framework
- Tests are located in the `tests/` directory
- Run tests with: `python3 -m unittest discover tests`

### Device Emulation
- Use `pretend_device` variable in `PortMaster/pugwash` to emulate different devices
- Available devices: rg351p, rg552, rg503, rg351v, rg353v, ogs, ogu, x55

## Common Tasks

### Adding New Features
1. Identify the appropriate module in `PortMaster/pylibs/harbourmaster/`
2. Add functionality following existing patterns
3. Update documentation if needed
4. Add tests for new functionality

### Refactoring
- Keep changes minimal and focused
- Maintain backward compatibility
- Preserve existing behavior
- Add tests to verify refactored code

### Debugging
- Check log output for errors
- Use logger from loguru for debugging
- Test with different device profiles

## Important Notes
- All file paths are relative to the PortMaster directory structure
- Port information is stored in `port.json` files within port directories
- The system tracks file renames using PM signatures embedded in bash scripts
