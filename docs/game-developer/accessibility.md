# Accessibility (WCAG 2.2 AA)

The runtime handles the mechanics: real form controls with labels, fieldsets and legends for groups,
keyboard operation (Tab, Space, Enter, arrow keys in tabs and radio groups), visible focus, 44 px touch
targets, focus moved to each new screen's heading, live regions for feedback and errors, a skip option,
reduced motion, light and dark themes, and text that scales with the reader's settings.

Your content has to do the rest:

- **Text carries the meaning.** Never rely on color, position, an image or a sound alone. Feedback tone is
  decoration; the words must say it.
- **Alt text** for every informative image: say what matters in context in one or two sentences. Use
  `"alt": ""` only for decoration. Don't put text inside images.
- **Audio** needs a transcript (required) and should have captions (`.vtt`). Never autoplay.
- **Plain language.** Short sentences, common words, one idea per screen. Aim for about a US grade 6–8
  reading level. Explain any term the chapter defines.
- **Labels** say exactly what to do ("Choose all that could be true"). Put instructions in `label` or
  `help`, not only in the body.
- **Sliders** need `minLabel` and `maxLabel`, so the scale is clear without seeing it.
- **No time limits, no flashing, no surprise sound.**
- **Keep screens short**: at most about five fields per form screen; split long forms into steps.
- **Options** should be distinguishable by their first words, which is how screen-reader users skim.
- **Sensitive content** gets content warnings in `contentWarnings`, which are shown before the game starts.
- **Summary** (`accessibility.summary`) tells readers what to expect before starting.

## Testing checklist

- Play the whole game with only the keyboard.
- Play it with VoiceOver (macOS: Cmd+F5) or NVDA: every screen heading is announced, every control has a
  name, feedback is read out.
- Zoom to 200% and use a 320 px wide window: nothing is cut off.
- Switch to dark mode and increase the site's text size.
