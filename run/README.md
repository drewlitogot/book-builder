# Double-click scripts

**One-time ChatGPT setup:** create a ChatGPT Project (for example named after your book), open its **Instructions**, and paste in all of `agents/chatgpt-project-instructions.md` (the Book Manager's Help tab can copy it for you). Then upload the reference files to the Project's **Files** (Help tab → *Show the files to upload*: editorial charter, outline, continuity notes). Start every chapter chat inside that project. ChatGPT can't see this repository; it only sees the prompt, the Instructions and those files.

| Script | What it does |
|---|---|
| `0-setup.command` | One-time setup (Pandoc, Typst, Python packages) |
| `Book Manager.command` | **Start here.** Opens the Book Manager in your browser: every chapter with its next step, saving ChatGPT replies (checked before saving), batch mode, overview of problems, building the PDF, and saving to GitHub. Keep its Terminal window open while you work; press **Quit** in the page to stop. |
| `Old menu.command` | The older pop-up dialog menu, kept in case you prefer it. |

The first time macOS blocks a script: right-click it → **Open** → **Open**.
