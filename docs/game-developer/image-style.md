# Image style for Book Builder games

Every game uses the same look, so activities feel like one book. This file is the single source: the
Book Manager pastes it into every game prompt, word for word.

## What each game gets

- **8 scene images, on 2 sheets.** Each sheet is **one** image divided into a 2×2 grid of four separate
  illustrations. Sheet 1 holds images 1–4, sheet 2 holds images 5–8.
- **1 icon.** A square image that stands for the activity on activity cards.

That's **9 images in 3 files**. The Book Manager cuts each sheet into its four images, so a sheet must be
large and cleanly divided.

Exception: for sensitive chapters (harassment, abuse, assault, sexual health, crisis), make **only the
icon** and no scene images.

## The house look (use in every image)

- **Medium:** calm, warm editorial illustration with soft gouache and pencil texture; gentle light; simple,
  uncluttered backgrounds. Not photorealistic, not 3D, not anime or cartoon.
- **Palette:** about 85% monochrome: ink black #171717, soft grays, warm off-white #F7F6F2. One or two small
  accents only, chosen from mustard #E3AC19, teal #0B858B and muted violet #926A98.
- **People:** ordinary adults of varied ages, genders, ethnicities, body types and visible disabilities, in
  everyday clothes and ordinary places (cafés, kitchens, parks, buses, living rooms, phones). Relaxed,
  natural poses; faces readable but not glamorous. The same characters keep the same look across all 8
  images (hair, clothes, build).
- **Never:** text, letters, numbers, captions, speech bubbles, logos, brand names, watermarks or UI; real or
  famous people; recognizable real places; sexual content or nudity; violence, injury, weapons, alcohol or
  drug use; anyone in distress being harmed; stereotypes of any group (show ordinary people in
  ordinary situations).

## Style block (start every image request with this)

> Calm, warm editorial illustration in soft gouache and pencil texture, gentle light, simple uncluttered
> background. Mostly monochrome: ink black #171717, soft grays and warm off-white #F7F6F2, with one or two
> small accents of mustard #E3AC19, teal #0B858B or muted violet #926A98. Ordinary, diverse adults in
> everyday places, natural poses. No text, letters, numbers, captions, speech bubbles, logos or
> watermarks.

## Sheet layout (scene images)

- One image per sheet, at the **highest resolution you can make**, landscape 3:2 (for example 2048×1365,
  or at least 1536×1024).
- Divided into a **2×2 grid of four equal panels**, edge to edge. No borders, frames, gutters, numbers or
  labels between or on the panels.
- Panel order: **top-left = first, top-right = second, bottom-left = third, bottom-right = fourth.**
- Each panel is a complete, separate scene composed for a 3:2 landscape crop. Keep faces and important
  details away from the panel edges (a thin margin is trimmed when the sheet is cut).
- Request to use: *"[style block] A 2×2 grid of four separate, equal landscape panels with no borders or
  gaps. Top-left: … Top-right: … Bottom-left: … Bottom-right: …"*

## Icon

- Square, **1024×1024**, the same style block, but simpler: one clear symbol or object for the activity
  (for example two coffee cups, a compass, a pair of speech-free chat shapes), centered on warm off-white
  #F7F6F2 with one accent color. No people's faces, no text. It must read clearly at 64 pixels.

## How to deliver and declare them

1. Generate the three images in the chat. Right above each one, write its label exactly:
   **Sheet 1**, **Sheet 2**, **Icon**.
2. In `game.json` `assets`, declare the 8 scene images **in panel order** (sheet 1 top-left first), then
   the icon:
   `assets/img-01-<short-name>.webp` … `assets/img-08-<short-name>.webp` and `assets/icon.png`, each with
   `"type": "image"` and `"alt"` text (one or two plain sentences on what matters in the picture; for the
   icon, a short phrase).
3. Add `"icon": "assets/icon.png"` to `game.json`, `"images"` to `requiredCapabilities`, and
   `"apiVersion": "1.1"` in both files.
4. Use every scene image once on a screen (`"image": {"asset": "assets/img-01-....webp"}`) or a perspective.
   Never let an image carry meaning the text doesn't also give.

The editor downloads the three files and the Book Manager asks for **Sheet 1**, **Sheet 2** and **Icon**. It
cuts, resizes and converts them, so file size doesn't matter, but resolution does.
