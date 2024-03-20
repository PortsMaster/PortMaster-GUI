## PortMaster Theme Specification

PortMasters new gui has a flexible theme system build around a `theme.json` file.

This is currently a WIP documenting the theme format.

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
- `port_info`: Detailed port information.
- `message_window`: A scrolling list of messages, used during downloading, installation, and fetching the latest ports information.
- `message_box`: An alert box
- `filter_list`: Available filters
- `themes_list`: List themes / downloader.

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

## Ports List tags

- ports_list.total_ports
- ports_list.filter_ports
- ports_list.filters

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
