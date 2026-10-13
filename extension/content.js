(() => {
  const BENCHMARK_TIMING = false;
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
  function hiddenInPage(node) {
    for (let current = node; current; current = current.parentElement) {
      if (hidden(current)) return true;
    }
    return false;
  }
  function extract(root) {
    const clone = root.cloneNode(true);
    const originals = [root, ...root.querySelectorAll("*")],
      copies = [clone, ...clone.querySelectorAll("*")];
    const semanticBlocks = new WeakSet();
    originals.forEach((node, i) => {
      if (
        [
          "block",
          "flow-root",
          "flex",
          "grid",
          "list-item",
          "table",
          "table-row",
          "table-cell",
          "table-caption",
        ].includes(getComputedStyle(node).display)
      )
        semanticBlocks.add(copies[i]);
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
    // Caption ownership is determined by a semantic line, not its paragraph.
    // ChatGPT can put a fact and its caption in one <p> separated by a newline.
    const isCaption = (anchor) =>
      citations.includes(anchor.href) &&
      !anchor.closest("table,pre,code") &&
      /^(?:\[\s*)?(?:source|citation|reference)\s*[:#]?\s*\d+(?:\s*\])?[.]?$/i.test(
        anchor.textContent.trim(),
      );
    const captionAnchors = new Set(
      [...clone.querySelectorAll("a[href]")].filter(isCaption),
    );
    const metadataAnchors = new Set();
    let line = [];
    function finishLine() {
      const firstAnchor = line.find((part) =>
        captionAnchors.has(part.anchor),
      )?.anchor;
      let block = firstAnchor?.parentElement;
      while (block && block !== clone && !semanticBlocks.has(block))
        block = block.parentElement;
      block ||= clone;
      let completePredecessor = false;
      if (firstAnchor) {
        const before = document.createRange();
        before.setStart(block, 0);
        before.setEndBefore(firstAnchor);
        completePredecessor = /[.!?][”'"\)\]]*$/.test(before.toString().trim());
      }
      let metadataTail = false;
      if (firstAnchor) {
        const lastAnchor = line
          .filter((part) => captionAnchors.has(part.anchor))
          .at(-1).anchor;
        const after = document.createRange();
        after.setStartAfter(lastAnchor);
        after.setEnd(block, block.childNodes.length);
        const remainder = after.cloneContents();
        remainder.querySelectorAll("a[href]").forEach((anchor) => {
          if (isCaption(anchor)) anchor.remove();
        });
        metadataTail = /^[\s,;·|()[\]–—-]*$/.test(remainder.textContent);
      }
      const isolatedBlock =
        block.textContent.trim() ===
        line
          .map((part) => part.text)
          .join("")
          .trim();
      if (
        firstAnchor &&
        (isolatedBlock || (completePredecessor && metadataTail)) &&
        line.every(
          (part) =>
            captionAnchors.has(part.anchor) ||
            /^[\s,;·|()[\]–—-]*$/.test(part.text),
        )
      )
        line.forEach((part) => {
          if (captionAnchors.has(part.anchor)) {
            metadataAnchors.add(part.anchor);
            // Later caption lines must see the factual predecessor, rather
            // than a previous metadata label becoming their predecessor.
            part.anchor.remove();
          }
        });
      line = [];
    }
    function captionLines(node) {
      if (node.nodeType === Node.TEXT_NODE) {
        const pieces = node.textContent.split(/\r?\n/);
        pieces.forEach((text, index) => {
          if (index) finishLine();
          line.push({ text, anchor: node.parentElement?.closest("a[href]") });
        });
        return;
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      if (node.tagName === "BR") {
        finishLine();
        node.replaceWith("\n");
        return;
      }
      const block = semanticBlocks.has(node);
      if (block) finishLine();
      [...node.childNodes].forEach(captionLines);
      if (block) finishLine();
    }
    captionLines(clone);
    finishLine();
    metadataAnchors.forEach((anchor) => anchor.remove());
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
    clone.querySelectorAll("*").forEach((node) => {
      if (semanticBlocks.has(node)) node.append("\n\n");
    });
    const text = clone.textContent.trim();
    return { text, citations };
  }
  function unavailableResponse(body) {
    return (
      body.citations.length === 0 &&
      /^this response couldn['’]t load[.!]?$/i.test(body.text.trim())
    );
  }
  function showUnavailable(root) {
    let ui = root.querySelector("[data-verifai]");
    if (ui?.dataset.verifai !== "unavailable") {
      ui?.remove();
      ui = document.createElement("div");
      ui.dataset.verifai = "unavailable";
      ui.textContent = "Not Verifiable: response unavailable.";
      root.append(ui);
    }
    snapshots.delete(root);
    for (const [id, value] of current) {
      if (value.root === root) current.delete(id);
    }
  }
  function inline(root, id, revision, text, runId, runSequence = 0) {
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
      ui.append(label, button);
      root.append(ui);
    }
    ui.querySelector("button").onclick = () =>
      chrome.runtime.sendMessage({ type: "details", id });
    ui.querySelector("[data-verifai-label]").textContent = text;
    current.set(id, { root, revision, runId, runSequence });
  }
  function responses() {
    const found = [
      ...document.querySelectorAll(
        '[data-message-author-role="assistant"][data-message-id]',
      ),
    ]
      .filter((root) => {
        const turn = root.closest("article") || root.parentElement;
        return (
          !hiddenInPage(root) &&
          turn?.querySelector(
            '[data-testid="copy-turn-action-button"]:not(:disabled):not([aria-disabled="true"])',
          )
        );
      })
      .map((root) => ({ root, body: root, messageId: root.dataset.messageId }));
    for (const root of document.querySelectorAll(
      "[data-chatgpt-selection-message-id]",
    )) {
      if (hiddenInPage(root)) continue;
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
            '.turn-action-controls button[aria-label="Copy"]:not(:disabled):not([aria-disabled="true"])',
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
  async function fingerprint(body) {
    return [
      ...new Uint8Array(
        await crypto.subtle.digest(
          "SHA-256",
          new TextEncoder().encode(JSON.stringify(body)),
        ),
      ),
    ]
      .map((x) => x.toString(16).padStart(2, "0"))
      .join("");
  }
  async function scan() {
    if (scanning || document.visibilityState !== "visible") return;
    scanning = true;
    try {
      const state = await chrome.runtime.sendMessage({
        type: "state",
        poll: true,
      });
      if (!state.active) return;
      if (
        document.querySelector(
          '[data-testid="stop-button"],button[aria-label="Stop"],button[aria-label="Stop generating"]',
        )
      )
        return;
      for (const { root, body: content, messageId } of responses()) {
        if (hiddenInPage(root) || hiddenInPage(content)) continue;
        const pageUrl = location.href;
        const body = extract(content);
        if (unavailableResponse(body)) {
          showUnavailable(root);
          continue;
        }
        if (!body.text || body.text.length > 60000) continue;
        const revision = await fingerprint(body);
        if (location.href !== pageUrl || !root.isConnected) continue;
        const before = snapshots.get(root);
        if (
          !before ||
          before.revision !== revision ||
          before.pageUrl !== pageUrl
        ) {
          root.querySelector("[data-verifai]")?.remove();
          for (const [id, value] of current) {
            if (value.root === root) current.delete(id);
          }
          snapshots.set(root, { revision, pageUrl, at: Date.now() });
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
          ...(BENCHMARK_TIMING
            ? {
                benchmarkStartedAt: Date.now(),
                benchmarkClock: "wall-clock-v3",
              }
            : {}),
        });
        if (response.accepted) {
          before.submitted = true;
          inline(
            root,
            id,
            revision,
            response.summary || "Analyzing claims",
            response.runId,
            response.runSequence,
          );
        }
      }
    } catch {
    } finally {
      scanning = false;
    }
  }
  async function responseEligible(id, revision) {
    if (
      document.visibilityState !== "visible" ||
      document.querySelector(
        '[data-testid="stop-button"],button[aria-label="Stop"],button[aria-label="Stop generating"]',
      )
    )
      return false;
    const pageUrl = location.href;
    const response = responses().find(
      (value) => id === new URL(pageUrl).pathname + ":" + value.messageId,
    );
    if (!response || hidden(response.root) || hidden(response.body))
      return false;
    const body = extract(response.body);
    if (unavailableResponse(body)) return false;
    const actual = await fingerprint(body);
    return (
      actual === revision &&
      location.href === pageUrl &&
      response.root.isConnected &&
      JSON.stringify(extract(response.body)) === JSON.stringify(body) &&
      responses().some(
        (value) => value.root === response.root && value.body === response.body,
      )
    );
  }
  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (message.type === "eligible") {
      responseEligible(message.id, message.revision)
        .then((eligible) => respond({ eligible }))
        .catch(() => respond({ eligible: false }));
      return true;
    }
    if (message.type === "verification-started") {
      const item = current.get(message.id);
      if (
        item?.revision === message.revision &&
        item.root.isConnected &&
        typeof message.runId === "string" &&
        Number.isSafeInteger(message.runSequence) &&
        message.runSequence > item.runSequence
      ) {
        item.runId = message.runId;
        item.runSequence = message.runSequence;
      }
      return;
    }
    if (message.type !== "result") return;
    (async () => {
      const item = current.get(message.id);
      if (
        item?.revision !== message.revision ||
        item.runId !== message.runId ||
        !item.root.isConnected
      )
        return;
      const pageUrl = location.href;
      const response = responses().find((value) => value.root === item.root);
      if (
        !response ||
        message.id !== new URL(pageUrl).pathname + ":" + response.messageId
      )
        return;
      const body = extract(response.body);
      const revision = await fingerprint(body);
      if (JSON.stringify(extract(response.body)) !== JSON.stringify(body))
        return;
      if (
        revision !== message.revision ||
        current.get(message.id)?.runId !== message.runId ||
        location.href !== pageUrl ||
        !item.root.isConnected
      )
        return;
      inline(
        item.root,
        message.id,
        message.revision,
        message.summary,
        message.runId,
        item.runSequence,
      );
    })().catch(() => {});
  });
  setInterval(scan, 2000);
})();
