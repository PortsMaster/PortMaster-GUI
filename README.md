# PortMaster - GUI

PortMaster is a convenient script designed to facilitate the downloading and installation of ports for handheld devices. As the number of available ports has increased, the original interface has become progressively cumbersome. For the past few months we have been developing a new GUI.

# Features (it has them)

- Completely custom GUI using Python SDL2 bindings
- Small size, only 11mb!
- Port previews, we can really showcase the ports.
- Cancellable downloads, accidentally started a 300mb download? Get out of here.
- Filter ports by genre/porter/runtime
- Localizations (We currently have English, Chinese, French, German, Italian, Japanese, Korean, Polish, Portuguese, and Spanish), translators welcome! [![Crowdin](https://badges.crowdin.net/portmaster/localized.svg)](https://crowdin.com/project/portmaster)
- **Themes:**
  - Since it was possible with the custom GUI, we went for it.
  - We have a few themes at launch, but contributions are more than welcome.
    - *Default Theme*: comes in both light mode and dark modes
    - *Zelda*: LTTP Inspired theme
    - *FF VII*: A beautifully done FF7 theme
    - *Basic Theme*: A super bare bones theme so you can get started designing your own!
  - Colour Schemes, themes can support multiple colour schemes for darkmode / lightmode / different colour ways.
  - Builtin theme downloader!

# Nerdy features

- **Custom Sources**: want to control your own ports repository? no worries!
- **Platform Hooks**: PortMaster on raspberry pi? Lets gooooo.

# Installation

[Install](https://portmaster.games/installation.html)


# Feedback

Please direct all feedback to the [PortMaster Public Beta](https://discord.com/channels/1122861252088172575/1144846802701520997) channel in the [PortMaster discord server](https://discord.gg/SbVcUM4qFp).


# Thanks

I want to thank everyone on the PortMaster crew who have helped, but a special thanks to:

- [christianhaitian](https://github.com/christianhaitian)
- [cebion](https://github.com/cebion)
- [christopher-roelofs](https://github.com/christopher-roelofs)
- [tekkenfede](https://github.com/tekkenfede)
- and so many more! :heart:

## Python libraries used:

- [ansimarkup][ansimarkup]
- [certifi][certifi]
- [colorama][colorama]
- [fastjsonschema][fastjsonschema]
- [idna][idna]
- [loguru][loguru]
- [port_gui][port_gui] - used as pySDL2gui
- [pypng][pypng]
- [pyqrcode][pyqrcode]
- [PySDL2][pysdl2]
- [requests][requests]
- [typing-extensions][typing_extensions]
- [urllib3][urllib3]


[PortMaster]: https://github.com/christianhaitian/PortMaster
[GitHubRepoV1]: https://github.com/kloptops/harbourmaster/tree/main/tools

[example_json]: https://github.com/kloptops/harbourmaster/blob/main/data/example.port.json
[port_html]: https://kloptops.github.io/harbourmaster/port.html
[known_ports]: https://github.com/kloptops/harbourmaster/tree/main/known-ports

[ansimarkup]: https://pypi.org/project/ansimarkup/
[certifi]: https://pypi.org/project/certifi/
[colorama]: https://pypi.org/project/colorama/
[fastjsonschema]: https://pypi.org/project/fastjsonschema/
[idna]: https://pypi.org/project/idna/
[loguru]: https://pypi.org/project/loguru/
[port_gui]: https://github.com/mcpalmer1980/port_gui
[pypng]: https://pypi.org/project/pypng/
[pyqrcode]: https://pypi.org/project/qrcode/
[pysdl2]: https://pypi.org/project/PySDL2/
[requests]: https://pypi.org/project/requests/
[typing_extensions]: https://pypi.org/project/typing-extensions/
[urllib3]: https://pypi.org/project/urllib3/
