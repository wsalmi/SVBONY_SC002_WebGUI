// SVBONY SC002 Console — vanilla JS, sem build step.
(() => {
  const $ = (sel, parent = document) => parent.querySelector(sel);
  const $$ = (sel, parent = document) => Array.from(parent.querySelectorAll(sel));
  const el = (tag, attrs = {}, ...children) => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "html") node.innerHTML = v;
      else if (k.startsWith("on") && typeof v === "function")
        node.addEventListener(k.slice(2).toLowerCase(), v);
      else if (v !== null && v !== undefined) node.setAttribute(k, v);
    }
    for (const c of children.flat()) {
      if (c === null || c === undefined) continue;
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return node;
  };

  const state = {
    catalog: null,
    currentGroup: null,
    showUnsupported: false,
  };

  async function fetchJSON(url, opts = {}) {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.error || res.statusText);
    return data;
  }

  async function loadCatalog() {
    state.catalog = await fetchJSON("/api/endpoints");
    renderSidebar();
    selectGroup(state.catalog.groups[0]);
  }

  function visibleItems(group) {
    const items = state.catalog.by_group[group] || [];
    if (state.showUnsupported) return items;
    return items.filter((e) => e.status !== "unsupported");
  }

  function renderSidebar() {
    const sidebar = $("#sidebar");
    sidebar.innerHTML = "";
    for (const group of state.catalog.groups) {
      const items = visibleItems(group);
      const a = el(
        "a",
        {
          class: "group" + (group === state.currentGroup ? " active" : ""),
          onclick: () => selectGroup(group),
        },
        group,
        el("span", { class: "count" }, group === "Advanced" ? "raw" : String(items.length))
      );
      sidebar.appendChild(a);
    }

    // Toggle "Mostrar unsupported"
    const toggle = el("label", { class: "sidebar-toggle" });
    const cb = el("input", { type: "checkbox" });
    if (state.showUnsupported) cb.checked = true;
    cb.addEventListener("change", () => {
      state.showUnsupported = cb.checked;
      renderSidebar();
      if (state.currentGroup) selectGroup(state.currentGroup);
    });
    toggle.appendChild(cb);
    toggle.appendChild(document.createTextNode(" mostrar unsupported"));
    sidebar.appendChild(toggle);
  }

  function selectGroup(group) {
    state.currentGroup = group;
    renderSidebar();
    const main = $("#main");
    main.innerHTML = "";
    main.appendChild(el("h2", { class: "muted" }, group));

    if (group === "Stream") {
      renderStreamPanel(main);
      return;
    }
    if (group === "Advanced") {
      renderRawConsole(main);
      return;
    }

    const items = visibleItems(group);
    if (items.length === 0) {
      main.appendChild(el("p", { class: "muted" }, "Nenhum endpoint visível nesta categoria. Marque 'mostrar unsupported' na barra lateral para ver tudo."));
      return;
    }
    for (const endpoint of items) {
      main.appendChild(renderEndpointCard(endpoint));
    }
  }

  function renderEndpointCard(endpoint) {
    const card = el("section", { class: "card" });
    const head = el(
      "div",
      { class: "endpoint-head" },
      el("h3", {}, endpoint.label),
      el("span", { class: "badge " + endpoint.status }, endpoint.status),
      el("span", { class: "risk " + endpoint.risk }, endpoint.risk)
    );
    card.appendChild(head);
    card.appendChild(el("p", { class: "desc" }, endpoint.description));

    const inputs = {};
    for (const inp of endpoint.inputs) {
      const row = el("div", { class: "form-row" });
      row.appendChild(el("label", {}, inp.label || inp.name));
      let field;
      if (inp.kind === "choice") {
        field = el("select", {});
        for (const choice of inp.choices) {
          const opt = el("option", { value: choice }, choice);
          if (inp.default && choice === inp.default) opt.selected = true;
          field.appendChild(opt);
        }
      } else if (inp.kind === "datetime") {
        field = el("input", { type: "datetime-local", value: inp.default || "" });
      } else if (inp.kind === "number") {
        field = el("input", { type: "number", value: inp.default || "", placeholder: inp.placeholder });
      } else {
        field = el("input", { type: "text", value: inp.default || "", placeholder: inp.placeholder });
      }
      inputs[inp.name] = field;
      row.appendChild(field);
      card.appendChild(row);
      if (inp.help) card.appendChild(el("p", { class: "muted", style: "margin: -4px 0 8px 138px; font-size: 12px;" }, inp.help));
    }

    const responseBox = el("div", { class: "response", style: "display: none;" });
    const runBtn = el(
      "button",
      {
        class: endpoint.risk === "DESTRUCTIVE" ? "danger" : "primary",
        onclick: async () => {
          if (endpoint.risk === "DESTRUCTIVE") {
            const conf = prompt(
              `Endpoint DESTRUTIVO: ${endpoint.label}\n` +
                `Digite "EXECUTAR" para confirmar.`
            );
            if (conf !== "EXECUTAR") return;
          }
          const payload = {};
          for (const [k, field] of Object.entries(inputs)) payload[k] = field.value;
          runBtn.disabled = true;
          runBtn.textContent = "Executando…";
          try {
            const data = await fetchJSON(`/api/call/${encodeURIComponent(endpoint.id)}`, {
              method: "POST",
              body: JSON.stringify(payload),
            });
            renderResponse(responseBox, data.result);
          } catch (e) {
            renderResponse(responseBox, { error: e.message, parsed_kind: "error" });
          } finally {
            runBtn.disabled = false;
            runBtn.textContent = "Executar";
          }
        },
      },
      "Executar"
    );
    card.appendChild(el("div", { class: "actions" }, runBtn));
    card.appendChild(responseBox);
    return card;
  }

  function renderResponse(box, result) {
    box.innerHTML = "";
    box.style.display = "block";
    const statusClass =
      result.status === 0
        ? "serr"
        : result.status < 300
        ? "s2xx"
        : result.status < 500
        ? "s4xx"
        : "s5xx";

    const meta = el(
      "div",
      { class: "meta" },
      el("span", { class: "status-pill " + statusClass }, result.status === 0 ? "ERR" : String(result.status)),
      el("span", { class: "muted mono" }, `${result.elapsed_ms ?? 0} ms`),
      el("span", { class: "muted mono" }, result.parsed_kind || "raw")
    );
    box.appendChild(meta);

    if (result.error) {
      box.appendChild(el("pre", {}, result.error));
    }

    if (result.parsed_kind === "key_value" && result.parsed?.pairs) {
      const table = el("table");
      const tbody = el("tbody");
      for (const [k, v] of Object.entries(result.parsed.pairs)) {
        tbody.appendChild(
          el("tr", {}, el("th", {}, k), el("td", {}, el("code", {}, String(v))))
        );
      }
      table.appendChild(tbody);
      box.appendChild(table);
      if (result.parsed.extra && result.parsed.extra.length) {
        box.appendChild(el("pre", {}, result.parsed.extra.join("\n")));
      }
    } else if (result.parsed_kind === "json") {
      // Renderização especial para getfilelist (lista de pastas+arquivos)
      if (
        result.parsed &&
        result.parsed.info &&
        Array.isArray(result.parsed.info) &&
        result.parsed.info[0] &&
        Array.isArray(result.parsed.info[0].files)
      ) {
        box.appendChild(renderFileList(result.parsed.info));
      } else {
        box.appendChild(el("pre", {}, JSON.stringify(result.parsed, null, 2)));
      }
    } else if (result.body_text) {
      box.appendChild(el("pre", {}, result.body_text));
    }

    if (result.curl_equivalent) {
      const row = el(
        "div",
        { class: "copy-row" },
        el("code", { class: "mono" }, result.curl_equivalent),
        el("button", { onclick: () => copyToClipboard(result.curl_equivalent) }, "Copiar curl")
      );
      box.appendChild(row);
    }
  }

  async function renderStreamPanel(main) {
    const card = el("section", { class: "card stream-card" });
    card.appendChild(el("h2", {}, "Streams disponíveis"));
    card.appendChild(
      el(
        "p",
        { class: "desc" },
        "Copie a URL e cole no VLC (Media → Open Network Stream), ou clique em 'Abrir no VLC' (macOS)."
      )
    );

    const placeholder = el("p", { class: "muted" }, "Consultando /app/getmediainfo…");
    card.appendChild(placeholder);
    main.appendChild(card);

    try {
      const data = await fetchJSON("/api/stream-urls");
      placeholder.remove();

      if (data.discovered?.rtsp) {
        const info = el(
          "p",
          { class: "muted" },
          "getmediainfo retornou: ",
          el("code", { class: "mono" }, JSON.stringify(data.discovered))
        );
        card.appendChild(info);
      }

      const ul = el("ul", { class: "urls" });
      for (const item of data.suggestions || []) {
        ul.appendChild(
          el(
            "li",
            {},
            el(
              "div",
              { style: "flex:1;display:flex;flex-direction:column;gap:2px;" },
              el("span", { style: "font-weight:500;" }, item.name),
              el("code", { class: "mono" }, item.url),
              el("span", { class: "muted", style: "font-size:11.5px;" }, item.note || "")
            ),
            el("button", { onclick: () => copyToClipboard(item.url) }, "Copiar"),
            el("button", { class: "primary", onclick: () => openInVlc(item.url) }, "Abrir no VLC")
          )
        );
      }
      card.appendChild(ul);

      card.appendChild(
        el(
          "p",
          { class: "muted", style: "margin-top: 12px;" },
          "Confirmado no probe: porta 554 e 6035 estão abertas. Path: /live/tcp/ch1. " +
            "Se uma variante não funcionar, tente a outra."
        )
      );
    } catch (e) {
      placeholder.textContent = "Falhou ao consultar: " + e.message;
    }
  }

  function renderRawConsole(main) {
    const card = el("section", { class: "card" });
    card.appendChild(el("h2", {}, "Console raw"));
    card.appendChild(
      el(
        "p",
        { class: "desc" },
        "Dispare qualquer request HTTP na câmera. Use isso para opções não expostas " +
          "nos cartões — o backend só repassa, sem validação."
      )
    );

    const methodSel = el(
      "select",
      {},
      el("option", { value: "GET" }, "GET"),
      el("option", { value: "POST" }, "POST"),
      el("option", { value: "HEAD" }, "HEAD")
    );
    const pathInp = el("input", {
      type: "text",
      placeholder: "/cgi-bin/Config.cgi",
      value: "/cgi-bin/Config.cgi",
    });
    const queryInp = el("textarea", {
      rows: "4",
      placeholder:
        "action=set\nproperty=Camera.Menu.HDR\nvalue=OFF\n\n(uma chave=valor por linha)",
    });

    const responseBox = el("div", { class: "response", style: "display: none;" });
    const runBtn = el(
      "button",
      {
        class: "primary",
        onclick: async () => {
          const query = queryInp.value
            .split("\n")
            .map((l) => l.trim())
            .filter(Boolean)
            .map((l) => {
              const i = l.indexOf("=");
              return i < 0 ? [l, ""] : [l.slice(0, i), l.slice(i + 1)];
            });
          runBtn.disabled = true;
          runBtn.textContent = "Executando…";
          try {
            const data = await fetchJSON("/api/raw", {
              method: "POST",
              body: JSON.stringify({
                method: methodSel.value,
                path: pathInp.value,
                query,
              }),
            });
            renderResponse(responseBox, data.result);
          } catch (e) {
            renderResponse(responseBox, { error: e.message, parsed_kind: "error" });
          } finally {
            runBtn.disabled = false;
            runBtn.textContent = "Executar";
          }
        },
      },
      "Executar"
    );

    card.appendChild(el("div", { class: "form-row" }, el("label", {}, "Method"), methodSel));
    card.appendChild(el("div", { class: "form-row" }, el("label", {}, "Path"), pathInp));
    card.appendChild(el("div", { class: "form-row" }, el("label", {}, "Query (k=v)"), queryInp));
    card.appendChild(el("div", { class: "actions" }, runBtn));
    card.appendChild(responseBox);
    card.appendChild(
      el(
        "details",
        { class: "raw-help" },
        el("summary", {}, "exemplos"),
        el(
          "ul",
          {},
          el("li", {}, el("code", {}, "GET /cgi-bin/Config.cgi  action=get  property=Camera.Menu.*")),
          el("li", {}, el("code", {}, "GET /cgi-bin/Config.cgi  action=set  property=Camera.Menu.HDR  value=OFF")),
          el("li", {}, el("code", {}, "GET /cgi-bin/hisnet/workmodecmd.cgi  -cmd=START")),
          el("li", {}, el("code", {}, "GET /app/getmediainfo"))
        )
      )
    );
    main.appendChild(card);
  }

  function renderFileList(folders) {
    const wrap = el("div", { class: "filelist" });
    let total = 0;
    for (const folder of folders) {
      const files = folder.files || [];
      total += files.length;
      const fset = el(
        "details",
        { open: files.length > 0 ? "" : null },
        el(
          "summary",
          {},
          el("strong", {}, folder.folder),
          el("span", { class: "muted", style: "margin-left:8px;" }, `(${files.length})`)
        )
      );
      if (files.length === 0) {
        fset.appendChild(el("p", { class: "muted", style: "margin: 6px 0 0 16px;" }, "vazio"));
      } else {
        const table = el("table");
        const tbody = el("tbody");
        tbody.appendChild(
          el(
            "tr",
            {},
            el("th", {}, "preview"),
            el("th", {}, "nome"),
            el("th", {}, "tipo"),
            el("th", {}, "tamanho"),
            el("th", {}, "duração"),
            el("th", {}, "data"),
            el("th", {}, "ações")
          )
        );
        for (const f of files) {
          const isVideo = f.type === 2;
          const dt = f.createtime ? new Date(f.createtime * 1000).toLocaleString() : "";
          const sizeKb = (f.size || 0) / 1024;
          const sizeStr =
            sizeKb > 1024 ? (sizeKb / 1024).toFixed(2) + " MB" : sizeKb.toFixed(1) + " KB";
          const duration = f.duration ? `${f.duration}s` : "—";
          const fileUrl = `/api/file?name=${encodeURIComponent(f.name)}`;
          const thumbUrl = `/api/thumbnail?name=${encodeURIComponent(f.name)}`;
          const thumbCell = el("td", { class: "thumb-cell" });
          if (isVideo) {
            const div = el("div", { class: "file-thumb video-thumb" }, "▶");
            thumbCell.appendChild(div);
          } else {
            const img = el("img", {
              src: thumbUrl,
              loading: "lazy",
              class: "file-thumb",
              alt: f.name,
            });
            img.addEventListener("error", () => {
              img.replaceWith(el("span", { class: "muted" }, "—"));
            });
            thumbCell.appendChild(img);
          }
          const actions = el("td");
          actions.appendChild(
            el(
              "button",
              {
                style: "margin-right:4px;",
                onclick: () => openPreview(f, fileUrl),
              },
              isVideo ? "▶ player" : "abrir"
            )
          );
          actions.appendChild(
            el(
              "a",
              {
                href: fileUrl,
                download: f.name.split("/").pop(),
                class: "btn-link",
                style: "margin-right:4px;",
              },
              "baixar"
            )
          );
          actions.appendChild(
            el(
              "button",
              {
                class: "danger",
                onclick: () => deleteFile(f.name),
              },
              "apagar"
            )
          );
          tbody.appendChild(
            el(
              "tr",
              {},
              thumbCell,
              el("td", {}, el("code", { class: "mono" }, f.name)),
              el("td", {}, isVideo ? "vídeo" : "foto"),
              el("td", {}, sizeStr),
              el("td", {}, duration),
              el("td", {}, dt),
              actions
            )
          );
        }
        table.appendChild(tbody);
        fset.appendChild(table);
      }
      wrap.appendChild(fset);
    }
    wrap.insertBefore(
      el("p", { class: "muted" }, `total: ${total} arquivos em ${folders.length} pastas`),
      wrap.firstChild
    );
    return wrap;
  }

  function openPreview(file, fileUrl) {
    const isVideo = file.type === 2;
    const overlay = el("div", { class: "preview-overlay" });
    const close = () => overlay.remove();
    overlay.addEventListener("click", (ev) => {
      if (ev.target === overlay) close();
    });
    const panel = el("div", { class: "preview-panel" });
    panel.appendChild(
      el(
        "div",
        { class: "preview-header" },
        el("code", { class: "mono" }, file.name),
        el("button", { class: "preview-close", onclick: close }, "✕")
      )
    );
    if (isVideo) {
      const video = el("video", {
        src: fileUrl,
        controls: "",
        autoplay: "",
        class: "preview-media",
      });
      panel.appendChild(video);
    } else {
      panel.appendChild(
        el("img", {
          src: fileUrl,
          class: "preview-media",
          alt: file.name,
        })
      );
    }
    panel.appendChild(
      el(
        "div",
        { class: "preview-footer" },
        el(
          "a",
          { href: fileUrl, download: file.name.split("/").pop(), class: "btn-link" },
          "baixar arquivo original"
        )
      )
    );
    overlay.appendChild(panel);
    document.body.appendChild(overlay);
    document.addEventListener(
      "keydown",
      function onKey(ev) {
        if (ev.key === "Escape") {
          close();
          document.removeEventListener("keydown", onKey);
        }
      }
    );
  }

  async function deleteFile(name) {
    if (!confirm(`Apagar ${name}? Isso é IRREVERSÍVEL.`)) return;
    try {
      const data = await fetchJSON("/api/call/app.deletefile", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      const info = data.result.parsed && data.result.parsed.info;
      const ok = data.result.parsed && data.result.parsed.result === 0;
      alert(
        (ok ? "OK: " : "FALHOU: ") +
          (info || `status ${data.result.status}`) +
          "\n\nClique em 'Lista de arquivos' de novo para atualizar."
      );
    } catch (e) {
      alert("erro: " + e.message);
    }
  }

  async function openInVlc(url) {
    try {
      const data = await fetchJSON("/api/open-in-vlc", {
        method: "POST",
        body: JSON.stringify({ url }),
      });
      if (!data.ok) alert("VLC: " + (data.error || data.stderr || "erro"));
    } catch (e) {
      alert("Falha: " + e.message);
    }
  }

  function copyToClipboard(text) {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text);
    } else {
      const ta = el("textarea", { style: "position: fixed; opacity: 0;" });
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
  }

  async function pollHealth() {
    try {
      const data = await fetchJSON("/api/health");
      const dot = $("#health-dot");
      const text = $("#health-text");
      if (data.online) {
        dot.classList.add("online");
        dot.classList.remove("offline");
        text.textContent = data.mock ? "mock OK" : "online";
      } else {
        dot.classList.add("offline");
        dot.classList.remove("online");
        text.textContent = data.mock ? "mock vazio" : "offline";
      }
    } catch {
      const dot = $("#health-dot");
      dot.classList.add("offline");
      dot.classList.remove("online");
      $("#health-text").textContent = "erro";
    }
  }

  document.addEventListener("DOMContentLoaded", async () => {
    await loadCatalog();
    pollHealth();
    setInterval(pollHealth, 10000);
  });
})();
