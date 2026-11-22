/* ==========================================================================
   NOUinnsikt — Statisk Kjelde- og Rådata-oppslag (Zero Backend, Pure Static)
   ========================================================================== */

(function () {
  "use strict";

  var DEFAULT_REPO_SLUG = "tordieltor/nouinnsikt-open-data";
  var PAGE_STEP = 20;

  function detectRepoSlug() {
    var host = (window.location.hostname || "").toLowerCase();
    var pathParts = (window.location.pathname || "").split("/").filter(Boolean);
    if (host.endsWith(".github.io") && pathParts.length >= 1) {
      var owner = host.replace(/\.github\.io$/, "");
      var repo = pathParts[0];
      if (owner && repo && repo !== "dokument") {
        return owner + "/" + repo;
      }
    }
    return DEFAULT_REPO_SLUG;
  }

  function hydrateGitHubLinks(repoSlug) {
    var ghBase = "https://github.com/" + repoSlug;
    var rawBase = "https://raw.githubusercontent.com/" + repoSlug + "/main/";

    document.querySelectorAll("[data-gh-root]").forEach(function (el) {
      el.setAttribute("href", ghBase);
    });
    document.querySelectorAll("[data-gh-releases]").forEach(function (el) {
      el.setAttribute("href", ghBase + "/releases");
    });
    document.querySelectorAll("[data-gh-path]").forEach(function (el) {
      var p = el.getAttribute("data-gh-path");
      if (p) {
        el.setAttribute("href", ghBase + "/" + p.replace(/^\/+/, ""));
      }
    });
    document.querySelectorAll("[data-gh-raw]").forEach(function (el) {
      var p = el.getAttribute("data-gh-raw");
      if (p) {
        el.setAttribute("href", rawBase + p.replace(/^\/+/, ""));
      }
    });
  }

  function normalizeText(str) {
    return String(str || "")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  function matchesDecade(year, decadeVal) {
    if (!decadeVal || decadeVal === "all") {
      return true;
    }
    var y = Number(year);
    var d = Number(decadeVal);
    if (d === 2020) {
      return y >= 2020 && y <= 2029;
    }
    if (d === 1970) {
      return y >= 1970 && y <= 1979;
    }
    return y >= d && y < d + 10;
  }

  function createBadge(text, className) {
    var span = document.createElement("span");
    span.className = "meta-badge " + className;
    span.textContent = text;
    return span;
  }

  function renderLookupItem(item) {
    var row = document.createElement("div");
    row.className = "lookup-item";
    row.setAttribute("role", "listitem");

    var main = document.createElement("div");
    main.className = "lookup-item-main";

    var badges = document.createElement("div");
    badges.className = "lookup-item-badges";
    badges.appendChild(createBadge(item.ref || ("NOU " + item.year), "badge-navy"));
    badges.appendChild(
      createBadge(item.nynorsk ? "Nynorsk" : "Bokmål", item.nynorsk ? "badge-sage" : "badge-navy")
    );
    if (item.podcast) {
      badges.appendChild(createBadge("MP3 i lydarkiv", "badge-amber"));
    }
    main.appendChild(badges);

    var titleEl = document.createElement("h3");
    titleEl.className = "lookup-item-title";
    titleEl.textContent = item.title || item.ref || ("NOU (" + item.id + ")");
    main.appendChild(titleEl);

    var metaParts = [];
    if (item.year) {
      metaParts.push("År: " + item.year);
    }
    if (item.leader) {
      metaParts.push("Utvalsleiar: " + item.leader);
    }
    if (item.ministry) {
      metaParts.push("Departement: " + item.ministry);
    }
    var metaEl = document.createElement("p");
    metaEl.className = "lookup-item-meta";
    metaEl.textContent = metaParts.join(" · ");
    main.appendChild(metaEl);

    var actions = document.createElement("div");
    actions.className = "lookup-item-actions";

    var idTag = document.createElement("span");
    idTag.className = "raw-id-tag";
    idTag.title = "Primærnøkkel i nous_flat.csv, nou_authors.csv, nou_chunks og lydarkivet";
    idTag.textContent = "nou_id: " + item.id;
    actions.appendChild(idTag);

    if (item.pdf_url) {
      var pdfLink = document.createElement("a");
      pdfLink.className = "btn-primary";
      pdfLink.href = item.pdf_url;
      pdfLink.target = "_blank";
      pdfLink.rel = "noopener noreferrer";
      pdfLink.textContent = "Offisiell PDF ↗";
      actions.appendChild(pdfLink);
    }

    if (item.source_url) {
      var srcLink = document.createElement("a");
      srcLink.className = "btn-secondary";
      srcLink.href = item.source_url;
      srcLink.target = "_blank";
      srcLink.rel = "noopener noreferrer";
      var isNb = item.source_url.indexOf("nb.no") !== -1;
      srcLink.textContent = isNb ? "NB.no ↗" : "Regjeringen.no ↗";
      actions.appendChild(srcLink);
    }

    row.appendChild(main);
    row.appendChild(actions);
    return row;
  }

  function initBibtexCopy() {
    var btn = document.getElementById("copy-bibtex-btn");
    var pre = document.getElementById("bibtex-snippet");
    if (!btn || !pre) {
      return;
    }
    btn.addEventListener("click", function () {
      var text = pre.textContent || "";
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
          btn.textContent = "Kopiert til utklippstavla ✓";
          setTimeout(function () {
            btn.textContent = "Kopier BibTeX";
          }, 2200);
        });
      }
    });
  }

  function initLookup() {
    var searchInput = document.getElementById("nou-search-input");
    var decadeSelect = document.getElementById("nou-decade-select");
    var nynorskCheckbox = document.getElementById("nou-nynorsk-only");
    var countText = document.getElementById("lookup-count-text");
    var resultsEl = document.getElementById("lookup-results");
    var moreBtn = document.getElementById("lookup-show-more");

    if (!searchInput || !resultsEl || !countText) {
      return;
    }

    var allItems = [];
    var filteredItems = [];
    var visibleCount = PAGE_STEP;

    var params = new URLSearchParams(window.location.search || "");
    var initialQuery = params.get("q");
    if (initialQuery) {
      searchInput.value = initialQuery;
    }

    function applyFilter(resetLimit) {
      if (resetLimit) {
        visibleCount = PAGE_STEP;
      }
      var q = normalizeText(searchInput.value);
      var tokens = q ? q.split(" ") : [];
      var decadeVal = decadeSelect ? decadeSelect.value : "all";
      var nynorskOnly = Boolean(nynorskCheckbox && nynorskCheckbox.checked);

      filteredItems = allItems.filter(function (item) {
        if (nynorskOnly && !item.nynorsk) {
          return false;
        }
        if (!matchesDecade(item.year, decadeVal)) {
          return false;
        }
        if (tokens.length === 0) {
          return true;
        }
        var hay = item._searchHaystack;
        for (var i = 0; i < tokens.length; i++) {
          if (hay.indexOf(tokens[i]) === -1) {
            return false;
          }
        }
        return true;
      });

      renderResults();
    }

    function renderResults() {
      resultsEl.textContent = "";
      var total = filteredItems.length;
      var slice = filteredItems.slice(0, visibleCount);

      if (total === 0) {
        countText.textContent = "Ingen treff blant 1 746 NOU-ar. Prøv eit anna søkeord eller nullstill filteret.";
        if (moreBtn) {
          moreBtn.hidden = true;
        }
        return;
      }

      countText.textContent =
        "Viser " +
        slice.length.toLocaleString("nn-NO") +
        " av " +
        total.toLocaleString("nn-NO") +
        " NOU-utgreiingar";

      var frag = document.createDocumentFragment();
      for (var i = 0; i < slice.length; i++) {
        frag.appendChild(renderLookupItem(slice[i]));
      }
      resultsEl.appendChild(frag);

      if (moreBtn) {
        var remaining = total - slice.length;
        if (remaining > 0) {
          moreBtn.hidden = false;
          moreBtn.textContent =
            "Vis " + Math.min(PAGE_STEP, remaining) + " fleire utgreiingar (" + remaining + " att)";
        } else {
          moreBtn.hidden = true;
        }
      }
    }

    fetch("./nou_lookup.json")
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error("HTTP " + resp.status);
        }
        return resp.json();
      })
      .then(function (data) {
        allItems = (Array.isArray(data) ? data : []).map(function (item) {
          item._searchHaystack = normalizeText(
            [item.id, item.slug, item.ref, item.title, item.year, item.leader, item.ministry].join(" ")
          );
          return item;
        });
        applyFilter(true);
      })
      .catch(function () {
        countText.textContent =
          "Kunne ikkje laste nou_lookup.json lokalt (bruk HTTP-server eller last ned nous_flat.csv frå GitHub-arkivet).";
      });

    searchInput.addEventListener("input", function () {
      applyFilter(true);
    });
    if (decadeSelect) {
      decadeSelect.addEventListener("change", function () {
        applyFilter(true);
      });
    }
    if (nynorskCheckbox) {
      nynorskCheckbox.addEventListener("change", function () {
        applyFilter(true);
      });
    }
    if (moreBtn) {
      moreBtn.addEventListener("click", function () {
        visibleCount += PAGE_STEP;
        renderResults();
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var slug = detectRepoSlug();
    hydrateGitHubLinks(slug);
    initBibtexCopy();
    initLookup();
  });
})();
