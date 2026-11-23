-- Turns perspective and neurotype fenced divs into labeled callout boxes.
--
--   ::: {.perspective for="women"}      ::: {.neurotype for="group-a"}
--   ...                                 ...
--   :::                                 :::
--
--   ::: {.partner for="group-a" title="If someone close to you works this way"}
--
-- Optional filtering: set metadata `only-perspective` or `only-neurotype`
-- (e.g. -M only-perspective=nonbinary) to drop callouts of that kind
-- for every other audience, producing an audience-specific edition.

local LABELS = {
  perspective = {
    men = "Men",
    women = "Women",
    nonbinary = "Non-binary",
  },
  neurotype = {
    ["group-a"] = "Group A",
    ["group-b"] = "Group B",
  },
}
-- Partner boxes (for the people around the reader) reuse the reader-group tags.
LABELS.partner = LABELS.neurotype

local only = {}

local function typst_escape(s)
  return (s:gsub("[\\\"]", "\\%0"))
end

local function make_callout(div, kind)
  local who = div.attributes["for"]
  local label = LABELS[kind][who]
  if not label then
    io.stderr:write(string.format(
      "[callouts] unknown %s value: %q\n", kind, tostring(who)))
    label = tostring(who)
  end
  if only[kind] and only[kind] ~= who then
    return {}
  end

  -- Readers may not know or want a label, so neurotype boxes show an
  -- experience-based title (title="If you lose track of time"), never the
  -- diagnosis. The `for` value stays as an internal tag for filtering.
  local heading = div.attributes["title"]
  if not heading or heading == "" then
    if kind == "perspective" then
      heading = "Perspective: " .. label
    else
      io.stderr:write(string.format(
        "[callouts] neurotype box for %q has no title; using a generic one\n", tostring(who)))
      heading = (kind == "partner") and "If this sounds like someone close to you" or "If this sounds like you"
    end
  end

  if FORMAT:match("typst") then
    local blocks = pandoc.List()
    blocks:insert(pandoc.RawBlock("typst", string.format(
      '#callout(kind: "%s", label: "%s")[', kind, typst_escape(heading))))
    blocks:extend(div.content)
    blocks:insert(pandoc.RawBlock("typst", "]"))
    return blocks
  end

  local content = pandoc.List()
  content:insert(pandoc.Para({ pandoc.Strong({ pandoc.Str(heading) }) }))
  content:extend(div.content)
  local attr = pandoc.Attr("", { "callout", kind, kind .. "-" .. who },
    { ["custom-style"] = "Callout" })
  return pandoc.Div(content, attr)
end

return {
  {
    Meta = function(meta)
      for _, kind in ipairs({ "perspective", "neurotype" }) do
        local v = meta["only-" .. kind]
        if v then only[kind] = pandoc.utils.stringify(v) end
      end
    end,
  },
  {
    -- Part headings get their own page in the PDF.
    Header = function(h)
      if h.level == 1 and h.classes:includes("part") and FORMAT:match("typst") then
        local title = pandoc.utils.stringify(h.content)
        return pandoc.RawBlock("typst",
          string.format('#part-title("%s")', typst_escape(title)))
      end
    end,
    Div = function(div)
      for _, kind in ipairs({ "perspective", "neurotype", "partner" }) do
        if div.classes:includes(kind) then
          return make_callout(div, kind)
        end
      end
    end,
  },
}
