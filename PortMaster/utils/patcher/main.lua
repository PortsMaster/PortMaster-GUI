-- Imports
local Talkies = require('talkies')
local push = require "push"

-- Constants
local gameWidth, gameHeight = 640, 480
local fontPath = "assets/font/PeaberryBase.ttf"
local fontSize = 16
local outputPaddingX = 24
local outputPaddingY = 12
local outputLineSpacing = 14
local outputTextColor = {0.314, 0.235, 0.482}
local spriteWidth, spriteHeight = 320, 240
local maxOutputLines = 12
local frameCount = 24
local patchboxFrameCount = 11
local frameRate = 12
local initialDialogDelay = 1
local gameName = "the game"
local patchTime = "5 minutes"
local isNews = false
local patchScript = "patch_script.sh"  -- Default patch script
local visibleOptionCount = 3

-- Variables
local patchOutput = {}
local patchInProgress = false
local showOutput = false
local font, cybion, spritesheet, patchImage
local currentFrame = 1
local animationTimer = 0
local animationDuration = 1 / frameRate
local timer = 0
local dialogShown = false
local optionShown = false
local patchChannel = love.thread.getChannel("patch_output")
local cancelChannel = love.thread.getChannel("cancel_patch")
local patchQuads = {}
local patchAnimationFrame = 1
local patchAnimationTimer = 0
local patchAnimationDuration = 2
local patchAnimationState = "idle"
local outputQueue = {}
local lineAddTimer = 0
local lineAddInterval = 0.1

local questionsFile, questions, questionAnswers = nil, nil, {}
local currentQuestionIndex = 0

-- Function to parse command-line arguments
local function parseCommandLineArguments()
    if arg and #arg > 0 then
        local i = 1
        while i <= #arg do
            if arg[i] == "-f" and arg[i + 1] and arg[i + 1] ~= "" then
                patchScript = arg[i + 1]
                i = i + 1
            elseif arg[i] == "-g" and arg[i + 1] and arg[i + 1] ~= "" then
                gameName = arg[i + 1]
                i = i + 1
            elseif arg[i] == "-t" and arg[i + 1] and arg[i + 1] ~= "" then
                patchTime = arg[i + 1]
                i = i + 1
            elseif arg[i] == "-q" and arg[i+1] then
                questionsFile = arg[i+1]
                local f = io.open(questionsFile, "r")
                if f then
                    local chunk = load(f:read("*a"), "@"..questionsFile, "t", _G)
                    f:close()
                    if chunk then
                        local ok, result = pcall(chunk)
                        if ok and type(result) == "table" then questions = result end
                    end
                end
            i = i + 1
            elseif arg[i] == "-n" then
                isNews = true
                i = i + 1
            else
                i = i + 1
            end
        end
    end
end

-- Function to initialize patch quads
function initPatchQuads()
    patchQuads = {}
    if patchImage then
        local imgW, imgH = patchImage:getDimensions()
        for x = 0, patchboxFrameCount - 1 do
            table.insert(patchQuads, love.graphics.newQuad(x * spriteWidth, 0, spriteWidth, spriteHeight, imgW, imgH))
        end
    end
end

-- Function to start patch animation
function startPatchAnimation(state)
    if #patchQuads == 0 then return end
    patchAnimationState = state
    patchAnimationTimer = 0
    if state == "preThread" then
        patchAnimationFrame = 1
    elseif state == "postThread" then
        patchAnimationFrame = patchboxFrameCount
    elseif state == "inThread" then
        patchAnimationFrame = patchboxFrameCount
    end
end

-- Function to wrap text to a maximum line length
function wrapText(text, limit)
    local wrappedText = {}
    local currentLine = ""
    for word in tostring(text):gmatch("%S+") do
        if #currentLine + #word + 1 > limit then
            table.insert(wrappedText, currentLine)
            currentLine = word
        else
            currentLine = (currentLine ~= "") and (currentLine .. " " .. word) or word
        end
    end

    table.insert(wrappedText, currentLine)
    return wrappedText
end

-- Read patch output from the channel
function readPatchOutput()
    local line = patchChannel:pop()  -- Attempt to read output
    if line then
        local wrappedLines = wrapText(line, 62)
        for _, wrappedLine in ipairs(wrappedLines) do
            table.insert(patchOutput, wrappedLine)
            if #patchOutput > maxOutputLines then  -- Keep the output limited
                table.remove(patchOutput, 1)
            end
        end

        -- Check for completion
        if line:find("Patching completed successfully!") then
            patchState = "complete"
            showOutput = false
            startPatchAnimation("postThread")
            patchInProgress = false
            return
        end

        -- Check for failure message
        if line:find("Patching process failed!") then
            patchState = "failed"
            showOutput = false
            startPatchAnimation("postThread")
            patchInProgress = false
            return
        end
    end
end

-- Function to start patching in a new thread
-- We actually start the PreThread animation here, and Update takes care of the PatchThread itself
function startPatchThread()
    startPatchAnimation("preThread")
end

-- Function to calculate Talkies height for questions
function calculateTalkiesHeight(questionText, visibleSlots)
    local lineHeight = font:getHeight()
    local qLines = wrapText(questionText or "", 62)
    local reservedOptions = math.min(#(questions[currentQuestionIndex].options or {}) + 2, visibleSlots + 2)
    local total = #qLines * lineHeight + math.max(reservedOptions, 1) * lineHeight + 20
    total = math.max(64, math.min(total, gameHeight - 40))
    return total
end

-- Function to display the next question
function showNextQuestion()
    if not questions then return startPatchThread() end
    currentQuestionIndex = currentQuestionIndex + 1
    if currentQuestionIndex > #questions then
        local env = ""
        for k,v in pairs(questionAnswers) do env = env .. k.."="..v.." " end
        if next(questionAnswers) then patchScript = env .. patchScript end
        return startPatchThread()
    end

    local q = questions[currentQuestionIndex]
    Talkies.height = calculateTalkiesHeight(q.question, visibleOptionCount)
    Talkies.y = gameHeight - Talkies.height - 8
    Talkies.inlineOptions = true

    local function presentWindow(startIndex)
        startIndex = startIndex or 1
        local remaining = #q.options - startIndex + 1
        local showCount = math.min(visibleOptionCount, remaining)
        local visible = {}
        for i=1, showCount do
            local idx = startIndex+i-1
            table.insert(visible, {idx=idx, text=q.options[idx][2], value=q.options[idx][1]})
        end

        local opts = {}
        if startIndex > 1 then table.insert(opts, {"Back", function() presentWindow(math.max(1, startIndex-visibleOptionCount)) end}) end
        for _,v in ipairs(visible) do
            table.insert(opts, {v.text, function() questionAnswers[q.id] = v.value; showNextQuestion() end})
        end
        if startIndex+showCount-1 < #q.options then table.insert(opts, {"More", function() presentWindow(startIndex+showCount) end}) end
        Talkies.say("Cybion", q.question, {image=cybion, thickness=2, options=opts})
    end

    presentWindow(1)
end

-- Function to show the initial Talkies dialog with two messages
function showInitialTalkiesDialog()
    if isNews then
        Talkies.say("Cybion", "Hello! Cybion again! The port for " .. gameName .. " has an update!", {
            image = cybion,
            thickness = 2,
            oncomplete = function()
                Talkies.say("Cybion", "Would you like to view it?", {
                    image = cybion,
                    thickness = 2,
                    options = {
                        {"View changelog", function() startPatchThread() end},
                        {"Continue", function() PatchCancelled() end}
                    }
                })
            end
        })
    else
        Talkies.say("Cybion", "Hello! Welcome to the PortMaster patching shop. Today we will be patching " .. gameName .. ".", {
            image = cybion,
            thickness = 2,
            oncomplete = function()
                if questions then
                    Talkies.say("Cybion", "The patch will take " .. patchTime .. ". First, I need to ask you a few questions.", {image = cybion, thickness = 2, oncomplete = showNextQuestion})
                else
                    Talkies.say("Cybion", "The patch will take " .. patchTime .. ". Press A to start the patching process.", {image = cybion, thickness = 2, oncomplete = startPatchThread})
                end
            end
        })
    end
    dialogShown = true
end

-- Function to show patch complete dialog
function PatchComplete()
    local message = isNews and "Don't forget to update the port with the PortMaster App later. On with the game!" or "Thank you for waiting, the patching process is complete! Press A to proceed to " .. gameName .. "."
    Talkies.say("Cybion", message, {
        thickness = 2,
        image = cybion,
        oncomplete = function()
            love.event.quit()
        end
    })
end

-- Function to show patch failed dialog
function PatchFailed()
    Talkies.say("Cybion", "Patching failed! Please go to the PortMaster Discord for help.", {
        thickness = 2,
        image = cybion,
        oncomplete = function()
            love.event.quit()
        end
    })
end

-- Function to show patch cancelled dialog
function PatchCancelled()
    if patchInProgress then
        cancelChannel:push("cancel")
        patchInProgress = false
        showOutput = false
    end
    local message = isNews and "Don't forget to update the port with the PortMaster App later. On with the game!" or "Patching has been canceled. Please try again later."
    Talkies.say("Cybion", message, {
        thickness = 2,
        image = cybion,
        oncomplete = function()
            love.event.quit()
        end
    })
end

-- Function to initialize and start the background music
function startBackgroundMusic()
    if not altLoopSound then
        altLoopSound = love.audio.newSource("assets/sfx/Eternity.ogg", "stream")
        altLoopSound:setLooping(true)
    end
    altLoopSound:play()
end

function love.load()
    parseCommandLineArguments()
    local windowWidth, windowHeight = love.window.getDesktopDimensions()
    push:setupScreen(gameWidth, gameHeight, windowWidth, windowHeight, {
        fullscreen = false,
        resizable = true,
        pixelperfect = false,
        highdpi = true
    })
    push:setBorderColor(1, 0.859, 0.686, 1)

    font = love.graphics.newFont(fontPath, fontSize)

    -- Load assets
    cybion = love.graphics.newImage("assets/gfx/cybionImage.png")
    cybion:setFilter("nearest", "nearest")
    spritesheet = love.graphics.newImage("assets/gfx/backgroundSheet.png")
    spritesheet:setFilter("nearest", "nearest")
    patchImage = love.graphics.newImage("assets/gfx/patchImage.png")
    patchImage:setFilter("nearest", "nearest")

    Talkies.talkSound = love.audio.newSource("assets/sfx/typeSound.ogg", "static")
    Talkies.optionOnSelectSound = love.audio.newSource("assets/sfx/optionSelect.ogg", "static")
    Talkies.optionSwitchSound = love.audio.newSource("assets/sfx/optionSwitch.ogg", "static")

    Talkies.font = font
    Talkies.characterImage = cybion
    Talkies.textSpeed = "fast"
    Talkies.inlineOptions = true
    if isNews then
        Talkies.height = 80
    end
    Talkies.messageBackgroundColor = {1.000, 0.851, 0.910}
    Talkies.messageColor = outputTextColor
    Talkies.messageBorderColor = outputTextColor
    Talkies.titleColor = outputTextColor

    initPatchQuads()
    startBackgroundMusic()
end

function love.update(dt)
    Talkies.update(dt)

    -- Update animation timer every frame
    animationTimer = animationTimer + dt
    if animationTimer >= animationDuration then
        animationTimer = animationTimer - animationDuration
        currentFrame = (currentFrame % frameCount) + 1
    end

    -- Handle dialog showing with a separate timer
    timer = timer + dt
    if not dialogShown and timer >= initialDialogDelay then
        showInitialTalkiesDialog()
        dialogShown = true
    end

    -- Update patch animation
    if patchAnimationState == "preThread" or patchAnimationState == "postThread" then
        patchAnimationTimer = patchAnimationTimer + dt
        local progress = math.min(patchAnimationTimer / patchAnimationDuration, 1)
        if patchAnimationState == "preThread" then
            patchAnimationFrame = math.floor(progress * (patchboxFrameCount - 1)) + 1
            if patchAnimationTimer >= patchAnimationDuration then
                patchAnimationState = "inThread"
                patchAnimationFrame = patchboxFrameCount
                patchInProgress = true
                showOutput = true
                local thread = love.thread.newThread("patch_thread.lua")
                thread:start(patchScript)
                cancelChannel:clear()
            end
        elseif patchAnimationState == "postThread" then
            patchAnimationFrame = patchboxFrameCount - math.floor(progress * (patchboxFrameCount - 1))
            -- Initiate Talkies dialog for patchState
            if patchAnimationTimer >= patchAnimationDuration then
                patchAnimationState = "idle"
                Talkies.height = nil
                if patchState == "complete" then
                    PatchComplete()
                elseif patchState == "failed" then
                    PatchFailed()
                elseif patchState == "cancelled" then
                    PatchCancelled()
                end
            end
        end
    end

    -- Read patch output from the thread
    if patchInProgress then
        readPatchOutput()  -- Check for output from the patch thread
        lineAddTimer = lineAddTimer + dt
        if lineAddTimer >= lineAddInterval and #outputQueue > 0 then
            table.insert(patchOutput, table.remove(outputQueue, 1))
            if #patchOutput > maxOutputLines then
                table.remove(patchOutput, 1)
            end
            lineAddTimer = lineAddTimer - lineAddInterval
        end
    end
end


function love.draw()
    push:start()

    -- Draw animated spritesheet background
    local frameX = (currentFrame - 1) * spriteWidth
    local windowWidth, windowHeight = push:getWidth(), push:getHeight()
    local scaleX = windowWidth / spriteWidth
    local scaleY = windowHeight / spriteHeight
    love.graphics.draw(spritesheet,
        love.graphics.newQuad(frameX, 0, spriteWidth, spriteHeight, spritesheet:getDimensions()),
        0, 0, 0, scaleX, scaleY)

    -- Draw patch dialog box
    if patchAnimationState ~= "idle" and patchQuads[patchAnimationFrame] then
        love.graphics.draw(patchImage, patchQuads[patchAnimationFrame], 0, 0, 0, scaleX, scaleY)
    end

    -- Draw patch output
    if showOutput then
        love.graphics.setFont(font)
        local outputY = math.max(windowHeight - #patchOutput * outputLineSpacing - outputPaddingY, 0)
        for i, line in ipairs(patchOutput) do
            love.graphics.setColor(outputTextColor)
            love.graphics.print(line, outputPaddingX, outputY + (i - 1) * outputLineSpacing)
        end

    end

    Talkies.draw()

    push:finish()
end

-- Handle gamepad inputs
function love.gamepadpressed(joystick, button)
    local currentDialog = Talkies.dialogs:peek()
    local isOptionDialog = currentDialog and currentDialog:showOptions()

    if button == "a" and not patchInProgress then
        Talkies.onAction()
    elseif button == "dpup" and isOptionDialog and not patchInProgress then
        Talkies.prevOption()
    elseif button == "dpdown" and isOptionDialog and not patchInProgress then
        Talkies.nextOption()
    elseif button == "b" then
        if isNews and patchInProgress then
            patchState = "cancelled"
            if showOutput then
                showOutput = false
                startPatchAnimation("postThread")
            end
        elseif not patchInProgress then
            Talkies.onAction()
        end
    end
end

function love.keypressed(key)
    local mapping = { 
        ["return"] = "a", 
        ["escape"] = "b", 
        ["up"] = "dpup", 
        ["down"] = "dpdown", 
        ["y"] = "y", 
        ["x"] = "x" 
    }
    if mapping[key] then 
        love.gamepadpressed(nil, mapping[key]) 
    end
end