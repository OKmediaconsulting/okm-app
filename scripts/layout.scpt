-- Jarvis Morning Layout
-- Schliesst alle bestehenden Chrome-Fenster und oeffnet 4 sauber im 2x2 Raster

set screenW to 3440
set screenH to 1440
set menuBar to 38

set halfW to screenW / 2
set halfH to (screenH - menuBar) / 2

set posTopLeft     to {0,     menuBar,          halfW,   menuBar + halfH}
set posTopRight    to {halfW, menuBar,          screenW, menuBar + halfH}
set posBottomLeft  to {0,     menuBar + halfH,  halfW,   screenH}
set posBottomRight to {halfW, menuBar + halfH,  screenW, screenH}

tell application "Google Chrome"
    -- Alle bestehenden Fenster schliessen
    close every window

    -- Kurz warten
    delay 0.5

    -- Fenster 1: Jarvis oben links (mit Morgenroutine)
    set w1 to make new window
    set URL of active tab of w1 to "http://localhost:8340/?morning=1"
    set bounds of w1 to posTopLeft

    -- Fenster 2: Gmail oben rechts
    set w2 to make new window
    set URL of active tab of w2 to "https://mail.google.com"
    set bounds of w2 to posTopRight

    -- Fenster 3: Google Kalender unten links
    set w3 to make new window
    set URL of active tab of w3 to "https://calendar.google.com"
    set bounds of w3 to posBottomLeft

    -- Fenster 4: Meta Business Suite unten rechts
    set w4 to make new window
    set URL of active tab of w4 to "https://business.facebook.com/latest/home"
    set bounds of w4 to posBottomRight

    activate
end tell
