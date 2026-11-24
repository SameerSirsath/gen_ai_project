// static/script.js — Dashboard frontend logic

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("outreach-form");
  const generateBtn = document.getElementById("generate-btn");
  const prospectNameInput = document.getElementById("prospect-name");
  const contextInput = document.getElementById("prospect-context");

  const statusBadge = document.getElementById("status-badge");
  const loadingSpinner = document.getElementById("loading-spinner");
  const emptyState = document.getElementById("empty-state");
  const resultsContainer = document.getElementById("results-container");

  const alertBanner = document.getElementById("alert-banner");
  const alertReasoning = document.getElementById("alert-reasoning");
  const flaggedSection = document.getElementById("flagged-section");
  const flaggedList = document.getElementById("flagged-list");

  const outputSubject = document.getElementById("output-subject");
  const outputBody = document.getElementById("output-body");
  const outputReasoning = document.getElementById("output-reasoning");
  const claimsUsedContainer = document.getElementById("claims-used-container");
  const wordCount = document.getElementById("word-count");
  const auditVerdict = document.getElementById("audit-verdict");

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();

      let prospectName = prospectNameInput ? prospectNameInput.value.trim() : "";
      if (!prospectName) {
        const h1El = document.querySelector("h1");
        if (h1El) prospectName = h1El.innerText.trim();
      }
      let context = contextInput ? contextInput.value.trim() : "";
      if (!context) {
        context = `${prospectName} enterprise organization and corporate operations.`;
        if (contextInput) contextInput.value = context;
      }

      if (!prospectName) {
        alert("Please provide the Prospect Name.");
        return;
      }

      // UI state: loading
      if (generateBtn) {
        generateBtn.disabled = true;
        const btnText = generateBtn.querySelector(".btn-text");
        if (btnText) btnText.textContent = "Running Pipeline...";
      }
      if (emptyState) emptyState.classList.add("hidden");
      if (resultsContainer) resultsContainer.classList.remove("hidden");
      if (loadingSpinner) loadingSpinner.classList.remove("hidden");

      if (statusBadge) {
        statusBadge.className = "badge badge-idle";
        statusBadge.textContent = "Processing...";
      }

    try {
      const response = await fetch("/api/generate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          prospect_name: prospectName,
          context: context,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || `Server responded with status ${response.status}`);
      }

      const data = await response.json();

      // UI state: show results
      loadingSpinner.classList.add("hidden");
      resultsContainer.classList.remove("hidden");

      // Populate draft fields
      outputSubject.textContent = data.subject || "(No subject generated)";
      outputBody.textContent = data.body || "(No body generated)";

      // Word count
      const words = (data.body || "").trim().split(/\s+/).filter(Boolean).length;
      wordCount.textContent = `${words} words`;

      // Evaluator reasoning
      outputReasoning.textContent = data.reasoning || "Evaluation completed.";

      // Populate verified claims used
      claimsUsedContainer.innerHTML = "";
      if (Array.isArray(data.claims_used) && data.claims_used.length > 0) {
        data.claims_used.forEach((claim) => {
          const tag = document.createElement("span");
          tag.className = "claim-tag";
          tag.textContent = claim;
          claimsUsedContainer.appendChild(tag);
        });
      } else {
        const tag = document.createElement("span");
        tag.className = "claim-tag";
        tag.textContent = "None listed";
        claimsUsedContainer.appendChild(tag);
      }

      // Check grounding verdict
      if (data.is_grounded && data.status === "PASSED") {
        // PASSED: Green badge
        statusBadge.className = "badge badge-passed";
        statusBadge.textContent = "PASSED";

        alertBanner.classList.add("hidden");
        flaggedSection.classList.add("hidden");
        flaggedList.innerHTML = "";
      } else {
        // BLOCKED: Red badge
        statusBadge.className = "badge badge-blocked";
        statusBadge.textContent = "BLOCKED";

        alertBanner.classList.remove("hidden");
        alertReasoning.textContent = data.reasoning || "Ungrounded or unsupported claims detected in the email draft.";

        // Populate flagged claims
        flaggedList.innerHTML = "";
        if (Array.isArray(data.flagged_claims) && data.flagged_claims.length > 0) {
          flaggedSection.classList.remove("hidden");
          data.flagged_claims.forEach((claim) => {
            const li = document.createElement("li");
            li.textContent = claim;
            flaggedList.appendChild(li);
          });
        } else {
          flaggedSection.classList.add("hidden");
        }
      }
    } catch (err) {
      if (loadingSpinner) loadingSpinner.classList.add("hidden");
      if (emptyState) emptyState.classList.remove("hidden");
      if (statusBadge) {
        statusBadge.className = "badge badge-idle";
        statusBadge.textContent = "Error";
      }
      alert(`Network or Server Error: ${err.message}`);
    } finally {
      if (generateBtn) {
        generateBtn.disabled = false;
        const btnText = generateBtn.querySelector(".btn-text");
        if (btnText) btnText.textContent = "Generate Outreach";
      }
    }
  });
}
});
