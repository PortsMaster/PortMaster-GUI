-- main.lua
local Talkies = require('talkies')
local push = require "push"

-- =====================
-- Constants
-- =====================
local GAME_WIDTH, GAME_HEIGHT = 640, 480
local FONT_PATH, FONT_SIZE = "assets/font/PeaberryBase.ttf", 16
local OUTPUT_PADDING_X, OUTPUT_PADDING_Y = 24, 12
local OUTPUT_LINE_SPACING, MAX_OUTPUT_LINES = 14, 12
local OUTPUT_TEXT_COLOR = {0.314, 0.235, 0.482}
local SPRITE_WIDTH, SPRITE_HEIGHT = 320, 240
local FRAME_COUNT, PATCHBOX_FRAME_COUNT, FRAME_RATE = 24, 11, 12
local INITIAL_DIALOG_DELAY = 1
local VISIBLE_OPTION_COUNT = 4

-- =====================
-- Variables
-- =====================
Talkies.inlineOptions = true

local font, cybion, spritesheet, patchImage
local currentFrame, animationTimer, animationDuration = 1, 0, 1 / FRAME_RATE
local timer, dialogShown = 0, false

local patchOutput, outputQueue = {}, {}
local patchInProgress, showOutput, patchState = false, false, "idle"
local patchChannel = love.thread.getChannel("patch_output")
local cancelChannel = love.thread.getChannel("cancel_patch")
local patchQuads = {}
local patchAnimationFrame, patchAnimationTimer, patchAnimationDuration = 1, 0, 2
local patchAnimationState = "idle"
local lineAddTimer, lineAddInterval = 0, 0.06

local patchScript = "patch_script.sh"
local gameName = "the game"
local patchTime = "5 minutes"
local isNews = false

local questionsFile, questions, questionAnswers = nil, nil, {}
local currentQuestionIndex = 0

local PatchComplete, PatchFailed, PatchCancelled

-- =====================
-- Helpers
-- =====================

local function parseCommandLineArguments()
    if not arg or #arg == 0 then return end
    local i = 1
    while i <= #arg do
        if arg[i] == "-f" and arg[i+1] then patchScript = arg[i+1]; i = i + 2
        elseif arg[i] == "-g" and arg[i+1] then gameName = arg[i+1]; i = i + 2
        elseif arg[i] == "-t" and arg[i+1] then patchTime = arg[i+1]; i = i + 2
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
            i = i + 2
        elseif arg[i] == "-n" then isNews = true; i = i + 1
        else i = i + 1 end
    end
end

local function wrapText(text, limit)
    local lines, line = {}, ""
    for word in tostring(text):gmatch("%S+") do
        if #line + #word + 1 > limit then
            if line ~= "" then table.insert(lines, line) end
            line = word
        else
            line = line ~= "" and (line .. " " .. word) or word
        end
    end
    if line ~= "" then table.insert(lines, line) end
    return #lines > 0 and lines or {""}
end

local function initPatchQuads()
    patchQuads = {}
    if patchImage then
        local imgW, imgH = patchImage:getDimensions()
        for x = 0, PATCHBOX_FRAME_COUNT - 1 do
            table.insert(patchQuads, love.graphics.newQuad(x*SPRITE_WIDTH, 0, SPRITE_WIDTH, SPRITE_HEIGHT, imgW, imgH))
        end
    end
end

local function startPatchAnimation(state)
    if #patchQuads == 0 then return end
    patchAnimationState = state
    patchAnimationTimer = 0
    if state == "preThread" then patchAnimationFrame = 1
    elseif state == "inThread" then patchAnimationFrame = PATCHBOX_FRAME_COUNT
    elseif state == "postThread" then patchAnimationFrame = PATCHBOX_FRAME_COUNT end
end

local function readPatchOutput()
    local line = patchChannel:pop()
    if not line then return end
    for _, l in ipairs(wrapText(line, 62)) do table.insert(outputQueue, l) end
    if line:find("Patching completed successfully!") then
        patchState = "complete"; startPatchAnimation("postThread"); patchInProgress = false
    elseif line:find("Patching process failed!") then
        patchState = "failed"; startPatchAnimation("postThread"); patchInProgress = false
    end
end

local function startPatchThread()
    startPatchAnimation("preThread")
end

local function calculateTalkiesHeight(questionText, visibleSlots)
    local lineHeight = font:getHeight()
    local qLines = wrapText(questionText or "", 62)
    local reservedOptions = math.min(#(questions[currentQuestionIndex].options or {}) + 2, visibleSlots + 2)
    local total = #qLines*lineHeight + math.max(reservedOptions,1)*lineHeight + 20
    total = math.max(64, math.min(total, GAME_HEIGHT-40))
    return total
end

-- =====================
-- Talkies dialogs
-- =====================
local function showNextQuestion()
    if not questions then return startPatchThread() end
    currentQuestionIndex = currentQuestionIndex + 1
    if currentQuestionIndex > #questions then
        local env = ""
        for k,v in pairs(questionAnswers) do env = env .. k.."="..v.." " end
        if next(questionAnswers) then patchScript = env .. patchScript end
        return startPatchThread()
    end

    local q = questions[currentQuestionIndex]
    Talkies.height = calculateTalkiesHeight(q.question, VISIBLE_OPTION_COUNT)
    Talkies.y = GAME_HEIGHT - Talkies.height - 8
    Talkies.inlineOptions = true

    local function presentWindow(startIndex)
        startIndex = startIndex or 1
        local remaining = #q.options - startIndex + 1
        local showCount = math.min(VISIBLE_OPTION_COUNT, remaining)
        local visible = {}
        for i=1, showCount do
            local idx = startIndex+i-1
            table.insert(visible, {idx=idx, text=q.options[idx][2], value=q.options[idx][1]})
        end

        local opts = {}
        if startIndex > 1 then table.insert(opts, {"Back", function() presentWindow(math.max(1, startIndex-VISIBLE_OPTION_COUNT)) end}) end
        for _,v in ipairs(visible) do
            table.insert(opts, {v.text, function() questionAnswers[q.id] = v.value; showNextQuestion() end})
        end
        if startIndex+showCount-1 < #q.options then table.insert(opts, {"More", function() presentWindow(startIndex+showCount) end}) end
        Talkies.say("Cybion", q.question, {image=cybion, thickness=2, options=opts})
    end

    presentWindow(1)
end

local function showInitialTalkiesDialog()
    if isNews then
        Talkies.say("Cybion", "Hello! Cybion again! The port for "..gameName.." has an update!", {image=cybion, thickness=2, oncomplete=function()
            Talkies.say("Cybion", "Would you like to view it?", {image=cybion, thickness=2, options={
                {"View changelog", startPatchThread},
                {"Continue", PatchCancelled}
            }})
        end})
    else
        Talkies.say("Cybion", "Hello! Welcome to the PortMaster patching shop. Today we will be patching "..gameName..".", {image=cybion, thickness=2, oncomplete=function()
            if questions then
                Talkies.say("Cybion", "The patch will take "..patchTime..". First, I need to ask you a few questions.", {image=cybion, thickness=2, oncomplete=showNextQuestion})
            else
                Talkies.say("Cybion", "The patch will take "..patchTime..". Press A to start the patching process.", {image=cybion, thickness=2, oncomplete=startPatchThread})
            end
        end})
    end
    dialogShown = true
end

-- =====================
-- Patch dialogs
-- =====================
function PatchComplete()
    Talkies.say("Cybion", isNews and "Update done! On with the game!" or "Patch complete! Press A to proceed to "..gameName..".", {thickness=2, image=cybion, oncomplete=love.event.quit})
end

function PatchFailed()
    Talkies.say("Cybion", "Patching failed! Please visit the PortMaster Discord for help.", {thickness=2, image=cybion, oncomplete=love.event.quit})
end

function PatchCancelled()
    if patchInProgress then cancelChannel:push("cancel"); patchInProgress=false; showOutput=false end
    Talkies.say("Cybion", isNews and "Update canceled. On with the game!" or "Patching canceled. Try again later.", {thickness=2, image=cybion, oncomplete=love.event.quit})
end

-- =====================
-- LOVE2D callbacks
-- =====================
function love.load()
    parseCommandLineArguments()
    local w,h = love.window.getDesktopDimensions()
    push:setupScreen(GAME_WIDTH, GAME_HEIGHT, w, h, {fullscreen=true, resizable=true, pixelperfect=false, highdpi=true})
    push:setBorderColor(1,0.859,0.686,1)

    font = love.graphics.newFont(FONT_PATH, FONT_SIZE)
    cybion = love.graphics.newImage("assets/gfx/cybionImage.png")
    cybion:setFilter("nearest","nearest")
    spritesheet = love.graphics.newImage("assets/gfx/backgroundSheet.png")
    spritesheet:setFilter("nearest","nearest")
    patchImage = love.graphics.newImage("assets/gfx/patchImage.png")
    patchImage:setFilter("nearest","nearest")

    Talkies.font = font
    Talkies.characterImage = cybion
    Talkies.textSpeed = "fast"
    Talkies.inlineOptions = true
    Talkies.talkSound = love.audio.newSource("assets/sfx/typeSound.ogg", "static")
    Talkies.optionOnSelectSound = love.audio.newSource("assets/sfx/optionSelect.ogg", "static")
    Talkies.optionSwitchSound = love.audio.newSource("assets/sfx/optionSwitch.ogg", "static")
    Talkies.height = 96
    Talkies.y = GAME_HEIGHT - Talkies.height - 8
    Talkies.messageBackgroundColor = {1,0.851,0.910}
    Talkies.messageColor = OUTPUT_TEXT_COLOR
    Talkies.messageBorderColor = OUTPUT_TEXT_COLOR
    Talkies.titleColor = OUTPUT_TEXT_COLOR

    initPatchQuads()
    if not altLoopSound then
        altLoopSound = love.audio.newSource("assets/sfx/Eternity.ogg","stream")
        altLoopSound:setLooping(true)
    end
    altLoopSound:play()
end

function love.update(dt)
    Talkies.update(dt)
    animationTimer = animationTimer + dt
    if animationTimer >= animationDuration then animationTimer = animationTimer - animationDuration; currentFrame = (currentFrame % FRAME_COUNT)+1 end

    timer = timer + dt
    if not dialogShown and timer >= INITIAL_DIALOG_DELAY then showInitialTalkiesDialog() end

    -- Patch animation handling
    if patchAnimationState~="idle" then
        patchAnimationTimer = patchAnimationTimer+dt
        local progress = math.min(patchAnimationTimer/patchAnimationDuration,1)
        if patchAnimationState=="preThread" then
            patchAnimationFrame = math.floor(progress*(PATCHBOX_FRAME_COUNT-1))+1
            if patchAnimationTimer>=patchAnimationDuration then
                patchAnimationState="inThread"; patchAnimationFrame=PATCHBOX_FRAME_COUNT
                patchInProgress=true; showOutput=true
                local thread=love.thread.newThread("patch_thread.lua")
                thread:start(patchScript); cancelChannel:clear()
            end
        elseif patchAnimationState=="postThread" then
            patchAnimationFrame = PATCHBOX_FRAME_COUNT - math.floor(progress*(PATCHBOX_FRAME_COUNT-1))
            if patchAnimationTimer>=patchAnimationDuration then
                patchAnimationState="idle"
                if patchState=="complete" then showOutput=false; PatchComplete()
                elseif patchState=="failed" then showOutput=false; PatchFailed()
                elseif patchState=="cancelled" then showOutput=false; PatchCancelled() end
            end
        end
    end

    if patchInProgress then readPatchOutput() end

    lineAddTimer = lineAddTimer + dt
    while lineAddTimer >= lineAddInterval and #outputQueue>0 do
        table.insert(patchOutput, table.remove(outputQueue,1))
        if #patchOutput>MAX_OUTPUT_LINES then table.remove(patchOutput,1) end
        lineAddTimer = lineAddTimer - lineAddInterval
    end
end

function love.draw()
    push:start()
    local frameX = (currentFrame-1)*SPRITE_WIDTH
    local w,h = push:getWidth(), push:getHeight()
    local scaleX,scaleY = w/SPRITE_WIDTH, h/SPRITE_HEIGHT

    love.graphics.draw(spritesheet,love.graphics.newQuad(frameX,0,SPRITE_WIDTH,SPRITE_HEIGHT,spritesheet:getDimensions()),0,0,0,scaleX,scaleY)
    if patchAnimationState~="idle" and patchQuads[patchAnimationFrame] then
        love.graphics.draw(patchImage, patchQuads[patchAnimationFrame],0,0,0,scaleX,scaleY)
    end

    if showOutput then
        love.graphics.setFont(font)
        local outputY = math.max(h - #patchOutput*OUTPUT_LINE_SPACING - OUTPUT_PADDING_Y,0)
        for i,line in ipairs(patchOutput) do
            love.graphics.setColor(OUTPUT_TEXT_COLOR)
            love.graphics.print(line, OUTPUT_PADDING_X, outputY + (i-1)*OUTPUT_LINE_SPACING)
        end
        love.graphics.setColor(1,1,1,1)
    end

    Talkies.draw()
    push:finish()
end

function love.gamepadpressed(_, button)
    local currentDialog = Talkies.dialogs:peek()
    local isOptionDialog = currentDialog and currentDialog:showOptions()

    if button=="a" and not patchInProgress then Talkies.onAction()
    elseif button=="dpup" and isOptionDialog and not patchInProgress then Talkies.prevOption()
    elseif button=="dpdown" and isOptionDialog and not patchInProgress then Talkies.nextOption()
    elseif button=="b" then
        if patchInProgress then patchState="cancelled"; cancelChannel:push("cancel"); patchInProgress=false; startPatchAnimation("postThread")
        else Talkies.onAction() end
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
