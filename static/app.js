// Expense Dashboard frontend - talks to the Flask REST API with fetch().

const form = document.getElementById("expense-form");
const formError = document.getElementById("form-error");
const rowsEl = document.getElementById("expense-rows");
const filterEl = document.getElementById("filter");
const submitBtn = document.getElementById("submit-btn");
const cancelBtn = document.getElementById("cancel-btn");

const COLORS = ["#2f6fdb", "#e8833a", "#2e9e6b", "#c94f7c", "#8b5cf6", "#d4a72c", "#6b7280"];
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "EUR" });

let expenses = [];
let categoryChart, monthChart;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

// ---------- Table ----------

async function loadExpenses() {
  const category = filterEl.value;
  const query = category ? `?category=${encodeURIComponent(category)}` : "";
  expenses = await api(`/api/expenses${query}`);
  renderTable();
}

function renderTable() {
  rowsEl.replaceChildren(...expenses.map(rowFor));
  document.getElementById("empty").hidden = expenses.length > 0;
}

function rowFor(expense) {
  const tr = document.createElement("tr");
  // textContent (not innerHTML) so user input can never inject HTML.
  const cells = [expense.spent_on, expense.description, expense.category, money.format(expense.amount)];
  cells.forEach((text, i) => {
    const td = document.createElement("td");
    td.textContent = text;
    if (i === 2) td.className = "tag";
    if (i === 3) td.className = "num";
    tr.append(td);
  });

  const actions = document.createElement("td");
  actions.className = "actions";
  actions.append(
    button("Edit", "link", () => startEdit(expense)),
    button("Delete", "link danger", () => deleteExpense(expense)),
  );
  tr.append(actions);
  return tr;
}

function button(label, className, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = label;
  b.className = className;
  b.addEventListener("click", onClick);
  return b;
}

// ---------- Form (add / edit) ----------

function resetForm() {
  form.reset();
  form.expense_id.value = "";
  form.spent_on.value = new Date().toISOString().slice(0, 10);
  document.getElementById("form-title").textContent = "Add expense";
  submitBtn.textContent = "Add";
  cancelBtn.hidden = true;
  formError.textContent = "";
}

function startEdit(expense) {
  form.expense_id.value = expense.id;
  form.description.value = expense.description;
  form.amount.value = expense.amount;
  form.category.value = expense.category;
  form.spent_on.value = expense.spent_on;
  document.getElementById("form-title").textContent = "Edit expense";
  submitBtn.textContent = "Save";
  cancelBtn.hidden = false;
  form.scrollIntoView({ behavior: "smooth", block: "center" });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    description: form.description.value,
    amount: form.amount.value,
    category: form.category.value,
    spent_on: form.spent_on.value,
  };
  const id = form.expense_id.value;
  try {
    await api(id ? `/api/expenses/${id}` : "/api/expenses", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    resetForm();
    await refresh();
  } catch (err) {
    formError.textContent = err.message;
  }
});

cancelBtn.addEventListener("click", resetForm);

async function deleteExpense(expense) {
  if (!confirm(`Delete "${expense.description}"?`)) return;
  await api(`/api/expenses/${expense.id}`, { method: "DELETE" });
  await refresh();
}

// ---------- Dashboard ----------

async function loadStats() {
  const stats = await api("/api/stats");
  document.getElementById("stat-month").textContent = money.format(stats.this_month);
  document.getElementById("stat-total").textContent = money.format(stats.total);
  document.getElementById("stat-count").textContent = stats.count;

  if (typeof Chart === "undefined") return; // Chart.js CDN not reachable
  categoryChart?.destroy();
  monthChart?.destroy();

  categoryChart = new Chart(document.getElementById("category-chart"), {
    type: "doughnut",
    data: {
      labels: stats.by_category.map((r) => r.category),
      datasets: [{ data: stats.by_category.map((r) => r.total), backgroundColor: COLORS }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "right" },
        tooltip: { callbacks: { label: (c) => `${c.label}: ${money.format(c.raw)}` } },
      },
    },
  });

  monthChart = new Chart(document.getElementById("month-chart"), {
    type: "bar",
    data: {
      labels: stats.by_month.map((r) => r.month),
      datasets: [{ label: "Spent", data: stats.by_month.map((r) => r.total), backgroundColor: COLORS[0], borderRadius: 4 }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => money.format(c.raw) } },
      },
      scales: { y: { beginAtZero: true, ticks: { callback: (v) => money.format(v) } } },
    },
  });
}

async function refresh() {
  await Promise.all([loadExpenses(), loadStats()]);
}

filterEl.addEventListener("change", loadExpenses);
resetForm();
refresh();
