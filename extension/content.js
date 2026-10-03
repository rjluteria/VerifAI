(() => {
  if (
    !["chatgpt.com", "chat.openai.com"].includes(location.hostname) ||
    location.protocol !== "https:"
  )
    return;
  const snapshots = new WeakMap();
  const current = new Map();
  let scanning = false;
  const hidden = (node) =>
    node.hidden ||
    node.getAttribute("aria-hidden") === "true" ||
    getComputedStyle(node).display === "none" ||
    getComputedStyle(node).visibility === "hidden";
  function extract(root) {
    const clone = root.cloneNode(true);
    const originals = [root, ...root.querySelectorAll("*")],
      copies = [clone, ...clone.querySelectorAll("*")];
    originals.forEach((node, i) => {
      if (hidden(node)) copies[i]?.remove();
    });
    clone
      .querySelectorAll("script,style,button,input,textarea,nav,[data-verifai]")
      .forEach((n) => n.remove());
    clone
      .querySelectorAll("img,canvas")
      .forEach((n) =>
        n.replaceWith("[Not Verifiable: image or chart content.]"),
      );
    clone.querySelectorAll("svg").forEach((n) => n.remove());
    const citations = [
      ...new Set(
        [...clone.querySelectorAll("a[href]")]
          .map((a) => a.href)
          .filter((url) => {
            try {
              const u = new URL(url);
              return (
                u.protocol === "https:" &&
                !["chatgpt.com", "chat.openai.com"].includes(u.hostname) &&
                (!u.port || u.port === "443") &&
                !u.username &&
                !u.password
              );
            } catch {
              return false;
            }
          }),
      ),
    ].slice(0, 12);
    clone.querySelectorAll("table").forEach((table) => {
      if (table.tHead?.rows.length > 1) {
        try {
          const rows = [...table.tHead.rows],
            grid = [];
          if (rows.length > 10 || table.tBodies.length !== 1)
            throw Error("unsupported table");
          rows.forEach((row, r) => {
            grid[r] ||= [];
            let c = 0;
            for (const cell of row.cells) {
              while (grid[r][c]) c++;
              if (
                cell.tagName !== "TH" ||
                cell.rowSpan < 1 ||
                cell.rowSpan > 10 ||
                cell.colSpan < 1 ||
                cell.colSpan > 10 ||
                r + cell.rowSpan > rows.length
              )
                throw Error("unsupported header");
              for (let dr = 0; dr < cell.rowSpan; dr++)
                for (let dc = 0; dc < cell.colSpan; dc++) {
                  grid[r + dr] ||= [];
                  if (grid[r + dr][c + dc]) throw Error("overlapping header");
                  grid[r + dr][c + dc] = cell.textContent.trim();
                }
              c += cell.colSpan;
            }
          });
          const width = grid[0].length;
          if (
            grid.some(
              (row) =>
                row.length !== width ||
                Array.from({ length: width }, (_, c) => !row[c]).some(Boolean),
            )
          )
            throw Error("ragged header");
          const columns = Array.from({ length: width }, (_, c) =>
            [...new Set(grid.map((row) => row[c]))].join(" / "),
          );
          const output = [...table.tBodies[0].rows].map((row) => {
            const values = [...row.cells];
            if (
              values.length !== width ||
              values[0].tagName !== "TH" ||
              values[0].getAttribute("scope") !== "row" ||
              values.some((cell) => cell.rowSpan !== 1 || cell.colSpan !== 1)
            )
              throw Error("ambiguous row");
            return values
              .map((cell, c) => `${columns[c]}: ${cell.textContent.trim()}`)
              .join("; ");
          });
          table.replaceWith(
            [
              table.caption?.textContent || "",
              ...output,
              table.tFoot?.textContent || "",
            ].join("\n"),
          );
        } catch {
          table.replaceWith("[Not Verifiable: ambiguous multi-level table.]");
        }
        return;
      }
      const cells = [...table.rows]
        .filter((row) => row.parentElement !== table.tFoot)
        .map((row) => [...row.cells]);
      const safe =
        cells.length > 1 &&
        cells[0].every((cell) => cell.tagName === "TH") &&
        cells.every(
          (row) =>
            row.length === cells[0].length &&
            row.every((cell) => cell.rowSpan === 1 && cell.colSpan === 1),
        );
      if (!safe) {
        table.replaceWith("[Not Verifiable: ambiguous table structure.]");
        return;
      }
      const headers = cells[0].map((cell) => cell.textContent.trim());
      const lines = cells
        .slice(1)
        .map((row) =>
          row
            .map((cell, i) => `${headers[i]}: ${cell.textContent.trim()}`)
            .join("; "),
        );
      table.replaceWith(
        [
          table.caption?.textContent || "",
          ...lines,
          table.tFoot?.textContent || "",
        ].join("\n"),
      );
    });
    clone
      .querySelectorAll("p,li,h1,h2,h3,h4,pre,blockquote")
      .forEach((node) => {
        node.append("\n\n");
      });
    const text = clone.textContent.trim();
    return { text, citations };
  }
  function inline(root, id, revision, text) {
    let ui = root.querySelector("[data-verifai]");
    if (!ui) {
      ui = document.createElement("div");
      ui.dataset.verifai = "result";
      ui.style.cssText =
        "font:13px system-ui;padding:10px;border:1px solid #888;border-radius:8px;margin-top:10px";
      const label = document.createElement("span");
      label.dataset.verifaiLabel = "1";
      const button = document.createElement("button");
      button.textContent = "View details";
      button.style.marginLeft = "10px";
      button.addEventListener("click", () =>
        chrome.runtime.sendMessage({ type: "details", id }),
      );
      ui.append(label, button);
      root.append(ui);
    }
    ui.querySelector("[data-verifai-label]").textContent = text;
    current.set(id, { root, revision });
  }
  function responses() {
    const found = [
      ...document.querySelectorAll(
        '[data-message-author-role="assistant"][data-message-id]',
      ),
    ]
      .filter((root) => {
        const turn = root.closest("article") || root.parentElement;
        return turn?.querySelector('[data-testid="copy-turn-action-button"]');
      })
      .map((root) => ({ root, body: root, messageId: root.dataset.messageId }));
    const complete = [
      ...document.querySelectorAll('[role="status"][aria-live]'),
    ].some((node) => node.textContent.trim() === "Response complete");
    if (!complete) return found;
    for (const root of document.querySelectorAll(
      "[data-chatgpt-selection-message-id]",
    )) {
      const unit = root.closest("[data-content-search-unit-key]");
      if (
        !unit?.querySelector(':scope > h4[data-conversation-role="assistant"]')
      )
        continue;
      const bodies = root.querySelectorAll(
        '[data-markdown-text-style="assistant-message"]',
      );
      if (bodies.length !== 1) continue;
      let turn = root,
        completed = false;
      for (
        let depth = 0;
        turn && depth <= 5;
        depth++, turn = turn.parentElement
      ) {
        if (
          turn.querySelectorAll(
            '[data-markdown-text-style="assistant-message"]',
          ).length !== 1
        )
          break;
        if (
          turn.querySelector(
            '.turn-action-controls button[aria-label="Copy"]:not(:disabled)',
          )
        ) {
          completed = true;
          break;
        }
      }
      const messageId = root.getAttribute("data-chatgpt-selection-message-id");
      if (
        completed &&
        messageId &&
        !found.some((item) => item.messageId === messageId)
      )
        found.push({ root, body: bodies[0], messageId });
    }
    return found;
  }
  async function scan() {
    if (scanning || document.visibilityState !== "visible") return;
    scanning = true;
    try {
      const state = await chrome.runtime.sendMessage({ type: "state" });
      if (!state.active) return;
      if (
        document.querySelector(
          '[data-testid="stop-button"],button[aria-label="Stop"],button[aria-label="Stop generating"]',
        )
      )
        return;
      for (const { root, body: content, messageId } of responses()) {
        if (hidden(root) || hidden(content)) continue;
        const pageUrl = location.href;
        const body = extract(content);
        if (!body.text || body.text.length > 60000) continue;
        const revision = [
          ...new Uint8Array(
            await crypto.subtle.digest(
              "SHA-256",
              new TextEncoder().encode(JSON.stringify(body)),
            ),
          ),
        ]
          .map((x) => x.toString(16).padStart(2, "0"))
          .join("");
        if (location.href !== pageUrl || !root.isConnected) continue;
        const before = snapshots.get(root);
        if (!before || before.revision !== revision) {
          snapshots.set(root, { revision, at: Date.now() });
          continue;
        }
        if (Date.now() - before.at < 1500 || before.submitted) continue;
        const id = new URL(pageUrl).pathname + ":" + messageId;
        const response = await chrome.runtime.sendMessage({
          type: "verify",
          url: pageUrl,
          id,
          revision,
          ...body,
        });
        if (response.accepted) {
          before.submitted = true;
          inline(root, id, revision, response.summary || "Analyzing claims");
        }
      }
    } catch {
    } finally {
      scanning = false;
    }
  }
  chrome.runtime.onMessage.addListener((message) => {
    if (message.type !== "result") return;
    const item = current.get(message.id);
    if (item?.revision === message.revision && item.root.isConnected)
      inline(item.root, message.id, message.revision, message.summary);
  });
  setInterval(scan, 2000);
})();
