const code = document.querySelector("#code");
const nums = document.querySelector("#nums");
const count = document.querySelector("#count");
const notice = document.querySelector("#notice");
const sample = `import os

def calculateTotal(items):
    result = 0
    for item in items:
        result = result + item
    return result

print(calculateTotal([2, 3, 5]))`;

function updateStats() {
  const lines = code.value ? code.value.split("\n").length : 1;
  nums.textContent = Array.from({length: lines}, (_, i) => i + 1).join("\n");
  count.textContent = `${lines} line${lines === 1 ? "" : "s"} · ${code.value.length} characters`;
}
function showNotice(text, type = "") {
  notice.textContent = text;
  notice.className = `notice visible ${type}`;
}
function hideNotice() { notice.className = "notice"; notice.textContent = ""; }
function loadSample() { code.value = sample; updateStats(); hideNotice(); }
function showView(view) {
  const analysis = view === "analysis";
  document.querySelector("#analysisView").classList.toggle("hidden", !analysis);
  document.querySelector("#historyView").classList.toggle("hidden", analysis);
  document.querySelector("#analysisNav").classList.toggle("active", analysis);
  document.querySelector("#historyNav").classList.toggle("active", !analysis);
  document.querySelector("#breadcrumb").textContent = analysis ? "Code analysis" : "Analysis history";
  if (!analysis) loadHistory();
}
async function checkStatus() {
  const label = document.querySelector("#cloudStatus");
  try {
    const response = await fetch("/api/status");
    const data = await response.json();
    label.textContent = data.database_connected ? "Cloud database connected" : "Analysis API online · DB pending";
  } catch { label.textContent = "Service status unavailable"; }
}
async function analyze() {
  hideNotice();
  const source = code.value;
  if (!source.trim()) { showNotice("Add Python code before starting an analysis.", "error"); code.focus(); return; }
  if (source.length > 100000) { showNotice("Please keep code below 100,000 characters.", "error"); return; }
  const button = document.querySelector("#analyze");
  button.disabled = true; button.textContent = "Analyzing…";
  try {
    const response = await fetch("/api/analyze", {
      method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({code: source})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Analysis failed.");
    document.querySelector("#empty").classList.add("hidden");
    document.querySelector("#results").classList.remove("hidden");
    document.querySelector("#resultState").textContent = data.syntax_error ? "Syntax error" : "Analysis complete";
    document.querySelector("#summaryTitle").textContent = data.syntax_error ? "Syntax check found a problem" : "Analysis complete";
    document.querySelector("#summaryText").textContent = data.issue_count === 0 ? "No issues were detected by the current rules." : `${data.issue_count} finding${data.issue_count === 1 ? "" : "s"} detected by the current rules.`;
    document.querySelector("#lines").textContent = data.line_count;
    document.querySelector("#issues").textContent = data.issue_count;
    document.querySelector("#saved").textContent = data.persisted ? "Yes" : "No";
    const list = document.querySelector("#findingList");
    list.replaceChildren();
    if (!data.findings.length) {
      const p = document.createElement("p"); p.className = "muted"; p.textContent = "No findings for the implemented rule set."; list.append(p);
    } else {
      for (const item of data.findings) {
        const card = document.createElement("article"); card.className = "finding";
        const top = document.createElement("div"); top.className = "finding-top";
        const title = document.createElement("h4"); title.textContent = `${item.line ? `Line ${item.line}: ` : ""}${item.title}`;
        const badge = document.createElement("span"); badge.className = `severity ${item.severity}`; badge.textContent = item.severity;
        top.append(title, badge);
        const message = document.createElement("p"); message.textContent = item.message;
        const suggestion = document.createElement("p"); suggestion.className = "suggestion"; suggestion.textContent = `Suggestion: ${item.suggestion}`;
        card.append(top, message, suggestion); list.append(card);
      }
    }
    if (!data.persisted) showNotice("Analysis succeeded, but this run was not saved. Configure DATABASE_URL in Render to enable cloud history.", "info");
    else showNotice("Analysis complete and saved to the cloud database.", "info");
    checkStatus();
  } catch (error) {
    showNotice(error.message || "Unable to reach the analysis service. Please try again.", "error");
  } finally { button.disabled = false; button.innerHTML = "✳ &nbsp; Analyze code ↗"; }
}
async function loadHistory() {
  const list = document.querySelector("#historyList");
  list.replaceChildren();
  const loading = document.createElement("p"); loading.className = "muted"; loading.textContent = "Loading history…"; list.append(loading);
  try {
    const response = await fetch("/api/history");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "History is unavailable.");
    list.replaceChildren();
    if (!data.runs.length) {
      const p = document.createElement("p"); p.className = "muted"; p.textContent = "No saved analyses yet. Analyze a snippet first."; list.append(p); return;
    }
    for (const run of data.runs) {
      const button = document.createElement("button"); button.className = "history-row";
      const left = document.createElement("span");
      const title = document.createElement("strong"); title.textContent = `Analysis #${run.id}`;
      const meta = document.createElement("small"); meta.textContent = `${new Date(run.created_at).toLocaleString()} · ${run.source_lines} lines · ${run.status}`;
      left.append(title, document.createElement("br"), meta);
      const right = document.createElement("span"); right.className = "history-count"; right.textContent = `${run.issue_count} finding(s)`;
      button.append(left, right); button.addEventListener("click", () => showHistoryDetail(run.id)); list.append(button);
    }
  } catch (error) {
    list.replaceChildren();
    const p = document.createElement("p"); p.className = "muted"; p.textContent = error.message; list.append(p);
  }
}
async function showHistoryDetail(id) {
  const list = document.querySelector("#historyList");
  try {
    const response = await fetch(`/api/history/${id}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not load this analysis.");
    list.replaceChildren();
    const back = document.createElement("button"); back.className = "secondary"; back.textContent = "← Back to history"; back.addEventListener("click", loadHistory); list.append(back);
    const heading = document.createElement("h3"); heading.textContent = `Analysis #${data.run.id}`; list.append(heading);
    const meta = document.createElement("p"); meta.className = "muted"; meta.textContent = `${data.run.source_lines} lines · ${data.run.issue_count} findings · ${new Date(data.run.created_at).toLocaleString()}`; list.append(meta);
    for (const item of data.findings) {
      const p = document.createElement("p"); p.className = "muted"; p.textContent = `${item.severity.toUpperCase()}${item.line ? ` · line ${item.line}` : ""} — ${item.title}: ${item.suggestion}`; list.append(p);
    }
    if (!data.findings.length) { const p = document.createElement("p"); p.className = "muted"; p.textContent = "No findings were recorded."; list.append(p); }
  } catch (error) { showNotice(error.message, "error"); }
}
document.querySelector("#load").addEventListener("click", loadSample);
document.querySelector("#reset").addEventListener("click", loadSample);
document.querySelector("#clear").addEventListener("click", () => { code.value = ""; updateStats(); hideNotice(); code.focus(); });
code.addEventListener("input", () => { updateStats(); hideNotice(); });
code.addEventListener("scroll", () => { nums.scrollTop = code.scrollTop; });
document.querySelector("#analyze").addEventListener("click", analyze);
document.querySelector("#analysisNav").addEventListener("click", () => showView("analysis"));
document.querySelector("#historyNav").addEventListener("click", () => showView("history"));
document.querySelector("#refreshHistory").addEventListener("click", loadHistory);
loadSample(); checkStatus();
