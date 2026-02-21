(function () {
    "use strict";

    const STORAGE_KEYS = {
        theme: "fruits_app_theme",
        history: "fruits_prediction_history",
    };

    const state = {
        selectedFile: null,
        lastResponse: null,
        history: [],
        chart: null,
        toast: null,
    };

    const elements = {
        body: document.body,
        themeToggle: document.getElementById("themeToggle"),
        dropZone: document.getElementById("dropZone"),
        imageInput: document.getElementById("imageInput"),
        browseBtn: document.getElementById("browseBtn"),
        previewWrapper: document.getElementById("previewWrapper"),
        previewImage: document.getElementById("previewImage"),
        analyzeBtn: document.getElementById("analyzeBtn"),
        resetBtn: document.getElementById("resetBtn"),
        statusBanner: document.getElementById("statusBanner"),
        loadingOverlay: document.getElementById("loadingOverlay"),
        resultCard: document.getElementById("resultCard"),
        fruitName: document.getElementById("fruitName"),
        confidenceBadge: document.getElementById("confidenceBadge"),
        confidenceText: document.getElementById("confidenceText"),
        confidenceBar: document.getElementById("confidenceBar"),
        confidenceExplanation: document.getElementById("confidenceExplanation"),
        resultImage: document.getElementById("resultImage"),
        predictionsList: document.getElementById("predictionsList"),
        probabilityChart: document.getElementById("probabilityChart"),
        downloadJsonBtn: document.getElementById("downloadJsonBtn"),
        clearHistoryBtn: document.getElementById("clearHistoryBtn"),
        historyList: document.getElementById("historyList"),
        historyEmpty: document.getElementById("historyEmpty"),
        toastRoot: document.getElementById("appToast"),
        toastMessage: document.getElementById("toastMessage"),
    };

    function init() {
        applyTheme(localStorage.getItem(STORAGE_KEYS.theme) || "light");
        loadHistory();
        bindEvents();
        renderHistory();
        maybeInitToast();
    }

    function bindEvents() {
        elements.themeToggle.addEventListener("click", toggleTheme);
        elements.browseBtn.addEventListener("click", () => elements.imageInput.click());
        elements.dropZone.addEventListener("click", () => elements.imageInput.click());
        elements.imageInput.addEventListener("change", onImageSelected);
        elements.analyzeBtn.addEventListener("click", analyzeImage);
        elements.resetBtn.addEventListener("click", resetState);
        elements.downloadJsonBtn.addEventListener("click", downloadLastResult);
        elements.clearHistoryBtn.addEventListener("click", clearHistory);

        ["dragenter", "dragover"].forEach((eventName) => {
            elements.dropZone.addEventListener(eventName, (event) => {
                event.preventDefault();
                elements.dropZone.classList.add("drag-active");
            });
        });

        ["dragleave", "drop"].forEach((eventName) => {
            elements.dropZone.addEventListener(eventName, (event) => {
                event.preventDefault();
                elements.dropZone.classList.remove("drag-active");
            });
        });

        elements.dropZone.addEventListener("drop", (event) => {
            const file = event.dataTransfer.files && event.dataTransfer.files[0];
            if (file) {
                setSelectedFile(file);
            }
        });
    }

    function maybeInitToast() {
        if (window.bootstrap && elements.toastRoot) {
            state.toast = new window.bootstrap.Toast(elements.toastRoot, { delay: 2800 });
        }
    }

    function onImageSelected(event) {
        const file = event.target.files && event.target.files[0];
        if (file) {
            setSelectedFile(file);
        }
    }

    function setSelectedFile(file) {
        if (!file.type.startsWith("image/")) {
            showStatus("danger", "Please upload a valid image file.");
            return;
        }

        state.selectedFile = file;
        const previewUrl = URL.createObjectURL(file);
        elements.previewImage.src = previewUrl;
        elements.resultImage.src = previewUrl;
        elements.previewWrapper.classList.remove("d-none");
        elements.analyzeBtn.disabled = false;
        showStatus("info", `Ready to analyze: ${file.name}`);
    }

    async function analyzeImage() {
        if (!state.selectedFile) {
            showStatus("warning", "Please choose an image before running prediction.");
            return;
        }

        const formData = new FormData();
        formData.append("file", state.selectedFile);

        setLoading(true);
        showStatus("info", "Sending image to DeepStack...");

        try {
            const response = await fetch("/api/predict", {
                method: "POST",
                body: formData,
            });

            const payload = await response.json().catch(() => ({
                success: false,
                error: "Server returned a non-JSON response.",
            }));

            if (!response.ok || !payload.success) {
                throw new Error(payload.error || `Prediction failed (HTTP ${response.status})`);
            }

            state.lastResponse = payload.data;
            renderPrediction(payload.data);
            addToHistory(payload.data);
            if (payload.fallback) {
                showStatus("warning", payload.warning || "Prediction generated using local fallback model.");
            } else {
                showStatus("success", `Prediction complete: ${payload.data.fruit}`);
            }
            showToast(`Detected ${payload.data.fruit} with ${payload.data.confidence_percent}% confidence.`);
        } catch (error) {
            showStatus("danger", error.message);
            showToast(error.message, true);
        } finally {
            setLoading(false);
        }
    }

    function renderPrediction(data) {
        const fruitEmoji = getFruitEmoji(data.fruit);
        elements.fruitName.textContent = `${fruitEmoji} ${data.fruit}`;
        elements.confidenceText.textContent = `${Number(data.confidence_percent).toFixed(1)}%`;
        elements.confidenceExplanation.textContent = data.confidence_explanation;
        elements.confidenceBar.style.width = `${Math.max(0, Math.min(100, data.confidence_percent))}%`;
        elements.confidenceBar.className = `progress-bar bg-${data.confidence_bar_class || "secondary"}`;
        elements.confidenceBadge.className = `badge rounded-pill text-bg-${badgeClassForLevel(data.confidence_level)}`;
        elements.confidenceBadge.textContent = (data.confidence_level || "unknown").toUpperCase();

        renderPredictionsList(data.predictions || []);
        renderChart(data.predictions || []);

        elements.downloadJsonBtn.disabled = false;
        elements.resultCard.classList.remove("d-none");
        elements.resultCard.classList.remove("revealed");
        void elements.resultCard.offsetWidth;
        elements.resultCard.classList.add("revealed");
    }

    function renderPredictionsList(predictions) {
        elements.predictionsList.innerHTML = "";

        if (!predictions.length) {
            const item = document.createElement("li");
            item.className = "list-group-item text-muted";
            item.textContent = "No prediction entries were returned.";
            elements.predictionsList.appendChild(item);
            return;
        }

        predictions.forEach((prediction, index) => {
            const item = document.createElement("li");
            item.className = "list-group-item";
            item.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <div class="fw-semibold">${index + 1}. ${prediction.label}</div>
                        <div class="prediction-meta">Raw confidence: ${prediction.confidence}</div>
                    </div>
                    <span class="history-value">${Number(prediction.confidence_percent).toFixed(1)}%</span>
                </div>
            `;
            elements.predictionsList.appendChild(item);
        });
    }

    function renderChart(predictions) {
        if (!window.Chart || !elements.probabilityChart) {
            return;
        }

        const labels = predictions.map((item) => item.label);
        const values = predictions.map((item) => Number(item.confidence_percent).toFixed(2));

        if (state.chart) {
            state.chart.destroy();
        }

        state.chart = new window.Chart(elements.probabilityChart, {
            type: "bar",
            data: {
                labels,
                datasets: [
                    {
                        label: "Confidence %",
                        data: values,
                        borderWidth: 0,
                        borderRadius: 10,
                        backgroundColor: "rgba(32, 81, 244, 0.7)",
                    },
                ],
            },
            options: {
                plugins: {
                    legend: {
                        display: false,
                    },
                },
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                    },
                },
            },
        });
    }

    function addToHistory(data) {
        const item = {
            fruit: data.fruit,
            confidence_percent: data.confidence_percent,
            timestamp_utc: data.timestamp_utc,
        };
        state.history.unshift(item);
        state.history = state.history.slice(0, 8);
        localStorage.setItem(STORAGE_KEYS.history, JSON.stringify(state.history));
        renderHistory();
    }

    function loadHistory() {
        try {
            const parsed = JSON.parse(localStorage.getItem(STORAGE_KEYS.history) || "[]");
            state.history = Array.isArray(parsed) ? parsed : [];
        } catch (error) {
            state.history = [];
        }
    }

    function clearHistory() {
        state.history = [];
        localStorage.removeItem(STORAGE_KEYS.history);
        renderHistory();
        showToast("Prediction history cleared.");
    }

    function renderHistory() {
        elements.historyList.innerHTML = "";
        const hasHistory = state.history.length > 0;
        elements.historyEmpty.classList.toggle("d-none", hasHistory);

        if (!hasHistory) {
            return;
        }

        state.history.forEach((entry) => {
            const item = document.createElement("li");
            item.className = "list-group-item";
            item.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <div class="fw-semibold">${entry.fruit}</div>
                        <div class="prediction-meta">${formatTimestamp(entry.timestamp_utc)}</div>
                    </div>
                    <div class="history-value">${Number(entry.confidence_percent).toFixed(1)}%</div>
                </div>
            `;
            elements.historyList.appendChild(item);
        });
    }

    function downloadLastResult() {
        if (!state.lastResponse) {
            showToast("No prediction result available to download.", true);
            return;
        }

        const blob = new Blob([JSON.stringify(state.lastResponse, null, 2)], {
            type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `fruit-prediction-${Date.now()}.json`;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
    }

    function resetState() {
        state.selectedFile = null;
        state.lastResponse = null;
        elements.imageInput.value = "";
        elements.previewWrapper.classList.add("d-none");
        elements.analyzeBtn.disabled = true;
        elements.statusBanner.innerHTML = "";
        elements.resultCard.classList.add("d-none");
        elements.downloadJsonBtn.disabled = true;
        if (state.chart) {
            state.chart.destroy();
            state.chart = null;
        }
    }

    function showStatus(type, message) {
        elements.statusBanner.innerHTML = `
            <div class="alert alert-${type} mb-0 py-2 px-3" role="alert">${message}</div>
        `;
    }

    function setLoading(isLoading) {
        elements.loadingOverlay.classList.toggle("d-none", !isLoading);
        elements.analyzeBtn.disabled = isLoading || !state.selectedFile;
    }

    function badgeClassForLevel(level) {
        if (level === "high") {
            return "success";
        }
        if (level === "medium") {
            return "warning";
        }
        if (level === "low") {
            return "danger";
        }
        return "secondary";
    }

    function getFruitEmoji(name) {
        const lower = (name || "").toLowerCase();
        if (lower.includes("apple")) {
            return "🍎";
        }
        if (lower.includes("banana")) {
            return "🍌";
        }
        if (lower.includes("orange")) {
            return "🍊";
        }
        if (lower.includes("strawberry")) {
            return "🍓";
        }
        if (lower.includes("tomato")) {
            return "🍅";
        }
        if (lower.includes("watermelon")) {
            return "🍉";
        }
        if (lower.includes("mango")) {
            return "🥭";
        }
        return "🍍";
    }

    function formatTimestamp(isoTimestamp) {
        if (!isoTimestamp) {
            return "Unknown time";
        }
        const parsed = new Date(isoTimestamp);
        if (Number.isNaN(parsed.getTime())) {
            return isoTimestamp;
        }
        return parsed.toLocaleString();
    }

    function showToast(message, isError) {
        if (!elements.toastMessage || !state.toast) {
            return;
        }
        elements.toastMessage.textContent = message;
        elements.toastRoot.classList.toggle("text-bg-danger", !!isError);
        elements.toastRoot.classList.toggle("text-bg-dark", !isError);
        state.toast.show();
    }

    function toggleTheme() {
        const newTheme = elements.body.classList.contains("theme-dark") ? "light" : "dark";
        applyTheme(newTheme);
    }

    function applyTheme(theme) {
        elements.body.classList.toggle("theme-dark", theme === "dark");
        localStorage.setItem(STORAGE_KEYS.theme, theme);
        elements.themeToggle.innerHTML =
            theme === "dark"
                ? '<i class="bi bi-sun"></i><span class="ms-1">Light Mode</span>'
                : '<i class="bi bi-moon-stars"></i><span class="ms-1">Dark Mode</span>';
    }

    init();
})();
