## PortMaster Theme Specification

PortMasters new gui has a flexible theme system build around a `theme.json` file.

This is currently a WIP documenting the theme format.

## Previewing your theme

The theme preview server renders every PortMaster screen with your theme, at any screen size, colour scheme and language, and refreshes the page each time you save a file. It runs from a PortMaster-GUI checkout on Linux or macOS:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt   # once, gets SDL2
.venv/bin/python tools/theme_server/serve.py --themes ~/my-themes
```

Then open http://localhost:8090/. `--themes` is one theme folder (it has a `theme.json`) or a folder of them; the default theme is always there too.

- **The screens:**
  - main menu, all, ready-to-run and installed ports, port info (and its popup)
  - filters, featured ports, options, runtimes, themes, colour schemes, language
  - on-screen keyboard, theme editor, messages with a progress bar, message box
  - the autoinstall and dialog screens, which always use the default theme on a device
  - the disclaimer and the unsupported-system warning, which are built in and look the same in every theme
  - They show the real ports list and screenshots, downloaded once into `~/.cache/portmaster-theme-server`. `--refresh-ports` gets the current ones.
- **Region boxes:** draws each region's area with its name. In a screen's own view, hover over or click a box (or a name in the list) to see the region's final theme values, after `#base`, `#element` and `[capability]` overrides are applied. **Save PNG** saves the screen, with the boxes if they're on.
- **One screen, every size:** one screen at every common resolution, to check your `[hires]`, `[4:3]` and other overrides.
- A screen your theme has no section for says so, rather than failing. Errors pugwash logged while drawing (a missing image, a bad colour) are listed on the screen.

To write the screens to files instead, for a theme's README or to compare before and after a change:

```bash
.venv/bin/python tools/theme_server/serve.py --themes ~/my-themes --export out/ \
    --resolutions 640x480,1280x720 --schemes all --langs en_US,de_DE
```

That writes `out/<theme>/<resolution>/<scheme>/<language>/<screen>.png`, with a `.json` next to each listing its regions.

### On your device

PortMaster carries the same server: **Options → Theme Editor** starts it on the device, and shows its address as text and as a QR code. Each device picks a random port the first time and keeps it, so the address stays the same. Open it on a computer or phone on the same network: no checkout or install needed. It previews the themes installed on the device, with the device's own ports list, and the translation editor saves into the device's PortMaster. Press B on the device to stop it.

- Translations saved on a device are in `PortMaster/pylibs/locales/` there. Copy them off before updating PortMaster, which replaces that folder.
- On a handheld (an RG35XX-H) the first screen takes 2-3 seconds, a new screen size about 2, switching theme, colour scheme or language (or saving) about a second, and each other screen half a second. Each screen size has a render process; how many are kept at once depends on the device's free memory.
- Anyone on the same network can open it while it runs.

### Translating PortMaster

The same server is a translation editor: pick **Translate** at the top. It lists every string of PortMaster (and, under **Themes**, every theme's text) with the chosen language's translation.
- **Filters:** show only the untranslated strings, those with problems, or those on the rendered screens.
- **Preview:** selecting a string shows the screens that use it, in that language, at the chosen resolution. Saving (leave the box, or Ctrl/⌘+Enter for the next string) updates them a moment later, so you can see whether it fits.
- **Problems flagged:** a translation that drops a `{placeholder}`, a line break, or a space the English starts or ends with (text joined to other text, like "Music: " + "Disabled").
- **Where it saves:** the language files in your checkout, `PortMaster/pylibs/locales/<lang>.json` and `<lang>.themes.json`. Pick a language marked "new" to start one.

A theme can also carry its own translations, in a `#translations` section of its `theme.json`:

```json
    "#translations": {
        "de_DE": { "Ports List": "Portliste" }
    },
```

They win over PortMaster's translations of the same text.

Every theme needs `main_menu`, `option_menu`, `ports_list` and `message_window` sections: pugwash fills in the other screens from those when a theme leaves them out.

## Scene Format

The theme has a few different sections:

- `#info`: Info about the theme
- `#base`: The base element, which every gui element in the theme inherits from
- `#pallet`: Predefined colours for the theme.
- `#resources`: Images the theme uses, can either be an atlas or individual images.
- `#elements`: Reusable elements that different scenes in your theme can use.
- **scenes**: Scenes that the gui uses

It also uses a template system for the text, so that the gui elements automatically update as the text changes.


## Element Inheritence Order:

The order that elemets get their values is defined as:

element -> scene `#base` -> global `#base`


If you use a reusable element the order is:

element -> element `#element` -> scene `#base` -> global `#base`


## Element overrides

You can override values in elements based on hardware by specifying a hardware capabilities on an attribute:

```json

    "#base": {
        "font": "DejaVuSans.ttf",
        "font-scale[hires]": 2.0,
        "font-scale[5:3,hires]": 3.0
    },

```

You can override entire elements based on hardware capabilities:

```json

        "ports_list": {
            "area": [0.0, 0.1, 0.4, 0.95],
            "border-x": 16,
            "roundness": 10,
            "font-size": 14,
            "font-color": "list_text",
            "select-color": "list_selected",
            "text-clip": true,
            "text-wrap": false,
            "autoscroll": "slide",
            "scroll-speed": 30,
            "scroll-delay-start": 500,
            "scroll-delay-end":   500
        },
        "ports_list[hires]": {
            "area": [0.0, 0.1, 0.3, 0.95]
        },
```

Since this uses the capabilities system used in ports you can add them together and or not them.


Currently the capabilities are:

- `hires`: devices with a screen resolution greater than 640:480
- `lowres`: devices with a screen resolution smaller then 640:480
- `power`: any device above an `rk3326` cpu.
- `opengl`: any device with `OpenGL`, not OpenGLES.
- `wide`: any aspect ratio above 4:3
- `3:2`: aspect ratio of 3:2
- `4:3`: aspect ratio of 4:3
- `5:3`: aspect ratio of 5:3
- `16:9`: aspect ratio of 16:9
- `427:240`: aspect ratio of 427:240 (ogs/ogu & friends)
- `480x320`: screen resolution of 480x320
- `640x480`: screen resolution of 640x480
- `854x480`: screen resolution of 854x480
- `960x544`: screen resolution of 960x544
- `1280x720`: screen resolution of 1280x720
- `1920x1152`: screen resolution of 1920x1152
- `language`: the current language (en_US, de_DE, es_ES, fr_FR, it_IT, and pl_PL)


You can combine them like so:

- `!lowres|hires`: must be exactly 640:480


## Scenes

Scenes can define their own `#base` element, which will cause all elements in that scene to inherit from.

Currently there are the following scenes:

- `main_menu`: The main menu
- `option_menu`: Options screen
- `ports_list`: The list of ports
- `port_info`: Detailed port information. X opens the port's links (`port_links`) when it has any; a theme that maps buttons in `#config` can use the action `port_links`.
- `port_links`: A port's links, its page on the PortMaster website (ports from the PortMaster and Multiverse sources) and the stores in its `port.json`, each as a QR code. The list is the region tagged `links_list`. The selected link is in `{port_links.name}` ("Steam", "itch.io", "PortMaster website", "Steam: developer", ...), `{port_links.url}` and `{port_links.kind}` (`website`, `store` or `developer`); `{port_links.count}` is how many there are. Show the QR code with `"image": "qr:{port_links.url}"`. A theme without this section (one made before it) gets one made from its `themes_list` section: its list, the QR code where the theme screenshot goes and the address where the description goes; if that has no `{theme_info.image}` region, a plain screen in PortMaster's own font.
- `message_window`: A scrolling list of messages, used during downloading, installation, and fetching the latest ports information.
- `message_box`: An alert box
- `filter_list`: Available filters
- `themes_list`: List themes / downloader.
- `theme_server`: The theme editor (Options → Theme Editor), with the tags `{theme_server.url}`, the address, empty until the server is up, and `{theme_server.status}`, the instructions or what went wrong. Show the address as a QR code with `"image": "qr:{theme_server.url}"`. A theme without this section gets one made from its `themes_list` section, as `port_links` does (the instructions where the list goes), or else a plain screen in PortMaster's own font.

### Scene: main_menu

This is the main menu scene, it requires the `option_list` element. It is the first scene to load and if backed out of will quit the program.

```json
    "main_menu": {
        "option_list": {
            "area": [ 0.0, 0.0, 1.0, 1.0 ],
            "font": "DejaVuSans.ttf",
            "font-size": 10,
            "list": []
        },
        "button_bar": {
            "area": [ 0.0, 8.0, 1.0, 1.0 ],
            "font": "DejaVuSans.ttf",
            "font-size": 10,
            "bar": []
        }
    }
```

The option_list can contain whatever text you feel is most appropriate, the actual option that gets called is the same option in the `option` list.

### Scene: options_menu

This is the options menu scene, it requires the `option_list` element. It is loaded from main-menu, this scene is reused for each subsequent option submenu.

```json
    "options_menu": {
        "option_list": {
            "area": [ 0.0, 0.0, 1.0, 1.0 ],
            "font": "DejaVuSans.ttf",
            "font-size": 10,
            "list": []
        },
        "button_bar": {
            "area": [ 0.0, 8.0, 1.0, 1.0 ],
            "font": "DejaVuSans.ttf",
            "font-size": 10,
            "bar": []
        }
    }
```

### Scene: ports_list

This is the main list of ports, it requires the `ports_list` element. It is loaded from main-menu, this scene is reused for listing ports for installing and uninstalling.

```json
    "ports_list": {
        "ports_list": {
            "area": [ 0.0, 0.0, 1.0, 1.0 ],
            "font": "DejaVuSans.ttf",
            "font-size": 10,
            "list": []
        },
        "button_bar": {
            "area": [ 0.0, 8.0, 1.0, 1.0 ],
            "font": "DejaVuSans.ttf",
            "font-size": 10,
            "bar": []
        }
    }
```


## Elements

### The basics

Elements are always rectangles, they must always have an `area` parameter. This can be pixels specifically, or a percentage of the parent area.

If you specify negative pixels for the width/height it subtracts it from the width/height of the parent area.

If you specify the coordinates in pixels it is in thef format: `x, y, width, height`

If you specify it as a percentage of the parent area it is as: `top-left-x, top-left-y, bottom-right-x, bottom-right-y`

```json

    "get_rect_perc": {
        // 25%, 25% to 75%, 75%
        "area": [0.25, 0.25, 0.75, 0.75]
    },

    "get_rect_px": {
        // same as above on a 640x480 display
        "area": [160, 120, 320, 240]
    },

    "get_rect_inset": {
        // same as above on a 640x480 display
        "area": [160, 120, -160, -120]
    },

```

As hinted to above, you can specify a parent element to use as the basis of the calculating element positions.


```json
        "left_pane": {
            // [0, 0, 192, 480] on 640x480 display
            "area": [ 0.0, 0.0, 0.3, 1.0 ]
        },
        "right_pane": {
            // [192, 0, 448, 480] on 640x480 display
            "area": [ 0.3, 0.0, 1.0, 1.0 ]
        },
        "port_info_image_area": {
            // [202, 10, 236, 230] using the above right_pane as the basis
            "parent": "right_pane",
            "area": [ 10, 10, -10, 0.5 ]
        },
        "port_info_text_area": {
            // [202, 240, 236, 230] using the above right_pane as the basis
            "parent": "right_pane",
            "area": [ 10, 0.5, -10, -10 ]
        },
```

By mixing and matching these you can build very powerful layouts.

You can also use the element overrides to further customise for different screen sizes.

```json
        "left_pane": {
            "area": [ 0.0, 0.0, 0.3, 1.0 ],
            "area[wide]": [ 0.0, 0.0, 0.4, 1.0 ]
        },
        "right_pane": {
            "area": [ 0.3, 0.0, 1.0, 1.0 ],
            "area[wide]": [ 0.4, 0.0, 1.0, 1.0 ]
        },
```


Elements can be themed by setting a `fill`, `outline`, `thickness`, and `roundness`:

- `fill`: the color to fill in the elements rect
- `outline`: the color of the outline for the elements rect
- `thickness`: how thick the stroke of the outline is
- `roundess`: if sdlGFX is available, it will make a roundrect with x pixels of roundness in the corners.
- `progress-fill`: this is a special fill colour, used for the progress bar.



### Displaying Text

Currently there are a few ways of displaying text.

To display text at a minimum you need a `font`, `font-size`, `font-color`, and `text`.

```json
    "text_element": {
        "area": [0.25, 0.25, 0.75, 0.75],
        "text": "Text to be displayed!",
        "font": "DejaVuSans.ttf",
        "font-size": 20,
        "font-color": [0, 0, 0]
    }
```

A special option is `font-scale` which should be used to broadly scale fonts across multiple elements or scenes using the element overrides.

```json
    "#base": {
        "font-scale[hires]": 2.0,
    }
```

You can align text to different positions of the element.

- `topleft`
- `topcenter`
- `topright`
- `midleft`
- `center`
- `midright`
- `bottomleft`
- `bottomcenter`
- `bottomright`

You can control the way text is displayed with word wrapping, automatic scrolling, clipping, and scaling.

- shrink/grow the text to fill the region: `"text-clip": false`
- clip the text and just show what is visible: `"text-clip": true`
- word wrap the text if it is too wide for the area provided: `"text-wrap": true`

It also supports text auto-scrolling if it doesnt fit within the area it is displayed. It will horizontally scroll if the text is wider (word wrap is off), and vertically scroll if it is too tall (word-wrap is on).

```json
    "element_name": {
        // Other element bits and bobs here.

        "text-clip": true,          // This must be true for scrolling to work
        "text-wrap": false,         // If text-wrap is false, it will default to a horizontal scroll, otherwise it defaults to a vertical scroll

        "autoscroll": "slide",      // null does nothing, "slide" scrolls down then resets, "marquee" scrolls back and forth

        "scroll-speed": 30,         // How many miliseconds between each scrolling step
        "scroll-delay-start": 500,  // How many miliseconds to wait before starting to scroll
        "scroll-delay-end":   500,   // How many miliseconds to wait at the end of scrolling

        "scroll-direction": "horizontal" // override the defaults assumed based on text-wrap
    }

```

### Images

Probably should write something here.

#### QR codes

An `image` starting with `qr:` is a QR code of the text after it, which can use text template tags. It's redrawn when a tag's value changes, and an empty text shows nothing.

```json
        "server_qr": {
            "area": [0.65, 0.2, 0.3, 0.4],
            "image": "qr:{some.url}",
            "image-mode": "fit"
        }
```

The code is black on white with a white border, as phone cameras read best, and it's scaled up without smoothing so it stays sharp at any size. Give it a square area, or `"image-mode": "fit"` (the default), so it isn't stretched.

### Lists

The list system is quite adequate

## Basic presentation options

```json
    "element_name": {
        "select-color":    [255, 128, 128],  // color to draw the selected item as
        "select-fill":     [128, 128, 128],  // color to fill behind the selected item
        "alt-fill":        [210, 210, 210],  // color to fill alternating rows
        "no-select-color": [128, 128, 128],  // color to draw text on unselectable rows.
        "no-select-fill":  [210, 210, 210],  // color to fill on unselectable rows.
        "inactive-select-color": [128,  64,  64],  // color to draw the selected item if the element is inactive
    }
```

## Pointer

```json
    "element_name": {
        "pointer": "pointer.png",                 // pointer image
        "pointer-align": ["midright", "midleft"], // poisition of (1) list/text to attach the position (2) of the pointer to
        "pointer-size": [128, 64],                // scale it to this size, otherwise use the size of the image provided
        "pointer-attach": "text",                 // attach to the rendered "text" rect, or the "list" item rect.
        "pointer-offset": [0, 0],                 // offset it by x,y pixels after the position is calculated.
        "pointer-flip-x": false,                  // flip the image horizontally
        "pointer-flip-y": false,                  // flip it vertically
        "pointer-mirror": false,                  // mirror the pointer and display on the other side of the list item
        "pointer-mirror-x": false,                // flip the mirrored pointer horizontally
        "pointer-mirror-y": false,                // flip the mirrored pointer vertically
    }
```

## Grid

Setting `list-columns` above 1 draws a list as a grid of tiles instead of rows. Each tile shows the item's image above its name. Only `ports_list` (in the `ports_list` and `featured_ports` scenes) supplies images, other lists will draw tiles with just the name.

```json
    "ports_list": {
        "list-columns": 3,            // number of columns (max 6) anything over will limit to 6, 1 (default) draws a normal list
        "list-columns[wide]": 4,      // can be overridden like any other value
        "item-size": 180,             // tile height, defaults to a 4:3 image plus one line of text
        "item-spacer": 8,             // gap between tiles
        "item-padding": 4,            // space between the tile edge and its image/name
        "alt-fill": [ 38, 42, 51 ],   // color to fill unselected tiles
        "select-fill": "accent",      // color to fill the selected tile
        "roundness": 10,              // rounds the tiles, and the image corners when the tile has a fill
        "line-height": 1.4,           // height of the name row, relative to the font
        "autoscroll": "marquee",      // scroll the selected name if it is too long
    }
```

In a grid LEFT/RIGHT move one tile, UP/DOWN move one row and L1/R1 move one page. The grid only scrolls when the selection moves off the visible rows.

**Note:** keep the grid to 30 visible tiles or fewer (columns x rows). Only 30 images are kept loaded, so a bigger grid has to reload its images from the SD card on every redraw, which is very slow. The number of rows depends on the tile height (`item-size`) and the screen size.

**Note:** only 30 images are kept loaded, and the grid loads a new one for every tile it shows, so scrolling quickly unloads older images. Any image a theme uses on its scenes (panels, icons, backgrounds) that is not listed in `#resources` can be unloaded while it is still on screen, which crashes PortMaster. List every static image in `#resources` so it is never unloaded:

```json
    "#resources": {
        "panel.png": {},
        "menu_icon.png": {}
    }
```


## Special Words

Within the templating system we have special words for things like button bindings and checkboxes. They are used for showing buttons and actions, and checkboxes.

It is possible to either override these special words with text, or replace them with an image.

| Special Word | Description               |
|--------------|---------------------------|
| `_A`         | Button A                  |
| `_B`         | Button B                  |
| `_X`         | Button X                  |
| `_Y`         | Button Y                  |
| `_UP`        | Button UP                 |
| `_DOWN`      | Button DOWN               |
| `_LEFT`      | Button LEFT               |
| `_RIGHT`     | Button RIGHT              |
| `_START`     | Button START              |
| `_SELECT`    | Button SELECT             |
| `_L`         | Button L                  |
| `_R`         | Button R                  |
| `_CHECKED`   | Checked item in a list    |
| `_UNCHECKED` | Unchecked item in a list  |

To replace the words with text you can simply add the following to your theme, like used in the `basic_theme`:

```json
    "#override": {
        "_A":         "A:",
        "_B":         "B:",
        "_X":         "X:",
        "_Y":         "Y:",
        "_UP":        "UP:",
        "_DOWN":      "DOWN:",
        "_LEFT":      "LEFT:",
        "_RIGHT":     "RIGHT:",
        "_START":     "START:",
        "_SELECT":    "SELECT:",
        "_L":         "L",
        "_R":         "R",
        "_CHECKED":   "[x]",
        "_UNCHECKED": "[  ]",
    }
```

To replace them with images you will need to load either images and use name to override the image name, or use an image atlas like in the `default_theme`.

```json
    "#resources": {
        "buttons.png": {
            "atlas": {
                "_A":         [  0,   0, 180, 180],
                "_B":         [180,   0, 180, 180],
                "_X":         [360,   0, 180, 180],
                "_Y":         [540,   0, 180, 180],
                "_UP":        [900, 360, 180,  90],
                "_DOWN":      [900, 450, 180,  90],
                "_LEFT":      [900, 180,  90, 180],
                "_RIGHT":     [990, 180,  90, 180],
                "_START":     [  0, 180, 360, 180],
                "_SELECT":    [360, 180, 360, 180],
                "_L":         [  0, 360, 270, 180],
                "_R":         [270, 360, 270, 180],
                "_CHECKED":   [900,   0, 180, 180],
                "_UNCHECKED": [720,   0, 180, 180]
            }
        }
    }
```

## Text Template System

PortMaster has a simple text templating engine, it supports tags and if/then/else statements.

You can use the tags in text areas and they will automatically update as their value changes.

An example of using the system.time_24hr tag:
```json
    {
        // Element options
        "text": "{system.time_24hr}"
    }
```

If no data is found for a tag the tag name is returned.

```json
    {
        // This will display "{system.unknown_tag}"
        "text": "{system.unknown_tag}"
    }
```

Obviously multiple tags can be used at once:

```json
    {
        // This might display "ArkOS (07232023)" on ArkOS for example"
        "text": "OS: {system.cfw_name} ({system.cfw_version})"
    }
```

As mentioned above you can use if/then/else statements in the text:

```json
    {
        // If port_info.runtime is not false it will display "\nRuntime: {}"
        "text": "{if:port_info.runtime}\nRuntime: {port_info.runtime} ({port_info.runtime_status}){else}No Runtime Required{endif}"
    }
```

You can even compare two tags text:

```json
    {
        // if ports_list.total_ports doesnt equal ports_list.filter_ports
        "text": "{if:!ports_list.total_ports::ports_list.filtered}{ports_list.filter_ports} / {ports_list.total_ports}{else}{ports_list.total_ports}{endif}"
    }
```

The format is:

`{if:[!]<KEYNAME>[:<EQUALS TEXT>[:OTHER KEY]]}<TRUTH TEXT>[{else}<ELSE TEXT>]{endif}`

### Hopefully this helps, if not... oh well i will write it better later on.

|  Tag                                                    |   Result                                              |
|---------------------------------------------------------|-------------------------------------------------------|
| `{if:!port_info.runtime}`                               | `port_info.runtime` != ""                             |
| `{if:port_info.runtime}`                                | `port_info.runtime` == ""                             |
| `{if:port_info.runtime:Mono 6.12.0.122}`                | `port_info.runtime` == "Mono 6.12.0.122"              |
| `{if:!port_info.runtime:Mono 6.12.0.122}`               | `port_info.runtime` != "Mono 6.12.0.122"              |
| `{if:ports_list.total_ports::ports_list.filter_ports}`  | `ports_list.total_ports` == `ports_list.filter_ports` |
| `{if:!ports_list.total_ports::ports_list.filter_ports}` | `ports_list.total_ports` != `ports_list.filter_ports` |


### System tags

- system.battery_level
- system.cfw_name
- system.cfw_version
- system.device_name
- system.free_space
- system.harbourmaster_version
- system.ip_address
- system.portmaster_version
- system.time_12hr
- system.time_24hr
- system.total_space
- system.used_space

- system.progress_text
- system.progress_amount

- system.progress_perc_5
- system.progress_perc_5_or_spinner
- system.progress_perc_10
- system.progress_perc_10_or_spinner
- system.progress_perc_20
- system.progress_perc_20_or_spinner
- system.progress_perc_25
- system.progress_perc_25_or_spinner
- system.progress_spinner_5
- system.progress_spinner_10
- system.progress_spinner_20
- system.progress_spinner_25

### Scene

- scene.title
- scene.tooltip

### Menu

- menu.selected

### Port info tags

- port_info.image
- port_info.title
- port_info.description
- port_info.instructions
- port_info.genres
- port_info.porter
- port_info.ready_to_run
- port_info.download_size
- port_info.install_size
- port_info.runtime
- port_info.runtime_status
- port_info.links: how many links the port has (the `port_links` screen), empty if none, so `{if:port_info.links}Press X for links{endif}` works.

## Ports List tags

- ports_list.total_ports
- ports_list.filter_ports
- ports_list.filters
- ports_list.position

## Featured Ports tags

- featured_ports.description
- featured_ports.image
- featured_ports.name

## Theme info tags

- theme_info.image
- theme_info.name
- theme_info.description
- theme_info.creator
- theme_info.status

## Runtime info tags

- runtime_info.name          # "Godot/FRT 2.1.6"
- runtime_info.status        # Installed / Uninstalled
- runtime_info.in_use        # Used / Not Used
- runtime_info.ports         # List of ports using the runtime: Blah, Blah 2, and Blah 3: Revenge of the Blah.
- runtime_info.verified      # Verified / Broken
- runtime_info.download_size # Download Size
- runtime_info.install_size  # Size on Disk


### Control flow of PortMaster

```
Main:
  -> Install Menu
  -> Uninstall Menu -> Port List [Installed filter]
  -> Options
  -> Quit

Install Menu:
  -> All Ports    -> Port List [No filter]
  -> Ready To Run -> Port List [RTR filter]

  -> Lists 1      -> Custom List
  -> Lists 2      -> Custom List
  -> Lists 3      -> Custom List
  -> Lists 4      -> Custom List

  -> Back

Port List:
  -> List of Ports
    -> Inspect
    -> Back

Options:
  -> TBD.
  -> Back

Inspect:
  -> Install/Re-Install or Uninstall
  -> Back

Install/Uninstall:
  -> Message Screen
  -> Back
```
