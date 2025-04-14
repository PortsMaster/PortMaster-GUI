local patchScript = ...  -- Get the patch script passed from main.lua

local patchChannel = love.thread.getChannel("patch_output")  -- Channel for output communication

-- Function to execute the patching process
local function runPatch()
    local process = io.popen(patchScript)

    -- Parsing state
    local inList = false
    local inQuote = false
    local inCode = false
    local inSpoiler = false
    local lastWasContent = false
    local skipLeadingBlanks = true -- Skip blanks until content

    -- Cached list item prefix
    local listItemPrefix = "  - "

    -- Inline tag stripping (optimized for lists)
    local function stripInlineTags(text)
        if not text:match("%[.-%]") then return text end -- Skip if no tags
        return text
            :gsub("%[b%](.-)%[/b%]", "%1")
            :gsub("%[i%](.-)%[/i%]", "%1")
            :gsub("%[u%](.-)%[/u%]", "%1")
            :gsub("%[strike%](.-)%[/strike%]", "%1")
            :gsub("%[url=.-%](.-)%[/url%]", "%1")
            :gsub("%[url%](.-)%[/url%]", "%1")
            :gsub("%[img%].-%[/img%]", "")
            :gsub("%[h1%](.-)%[/h1%]", "%1")
            :gsub("%[color=.-%](.-)%[/color%]", "%1")
            :gsub("%[size=.-%](.-)%[/size%]", "%1")
            :gsub("%[%w+.-%]", "")
            :gsub("%[/%w+%]", "")
    end

    while true do
        local line = process:read("*line")  -- Read output line by line
        if not line then
            break  -- Exit the loop if no more output
        end

        local trimmed = line:match("^%s*(.-)%s*$") -- Trim whitespace

        -- Skip empty lines until content
        if trimmed == "" then
            if not (inCode or inQuote or inSpoiler) and lastWasContent and not skipLeadingBlanks then
                patchChannel:push("")
                lastWasContent = false
            end
            goto continue
        end

        -- From here, we have non-empty content
        skipLeadingBlanks = false

        if inCode then
            if trimmed:match("^%[/code%]") then
                inCode = false
                if lastWasContent then
                    patchChannel:push("")
                end
                lastWasContent = false
            else
                patchChannel:push("  " .. trimmed)
                lastWasContent = true
            end
        elseif inQuote then
            if trimmed:match("^%[/quote%]") then
                inQuote = false
                if lastWasContent then
                    patchChannel:push("")
                end
                lastWasContent = false
            else
                patchChannel:push("> " .. trimmed)
                lastWasContent = true
            end
        elseif inSpoiler then
            if trimmed:match("^%[/spoiler%]") then
                inSpoiler = false
                if lastWasContent then
                    patchChannel:push("")
                end
                lastWasContent = false
            else
                patchChannel:push("(Spoiler) " .. trimmed)
                lastWasContent = true
            end
        elseif trimmed:match("^%[list%]") then
            inList = true
        elseif trimmed:match("^%[/list%]") then
            inList = false
            if lastWasContent then
                patchChannel:push("")
            end
            lastWasContent = false
        elseif trimmed:match("^%[code%]") then
            inCode = true
        elseif trimmed:match("^%[quote.*%]") then
            inQuote = true
        elseif trimmed:match("^%[spoiler%]") then
            inSpoiler = true
        elseif trimmed:match("^%[%*%]") then
            local item = trimmed:match("^%[%*%]%s*(.*)$") or ""
            local processed = stripInlineTags(item)
            if processed ~= "" then
                patchChannel:push(listItemPrefix .. processed)
                lastWasContent = true
            end
        else
            -- Regular text or section header
            local processed = stripInlineTags(trimmed)
            if processed ~= "" then
                local prefix = inList and "  " or ""
                patchChannel:push(prefix .. processed)
                lastWasContent = true
            end
        end

        ::continue::
    end

    local exitCode = process:close() 

    -- Always notify success after the patch script has completed.
    patchChannel:push("Patching completed successfully!") 
end

runPatch() 