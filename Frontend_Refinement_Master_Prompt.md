# MASTER PROMPT: SAAS FRONTEND LAYOUT REFINEMENT (FLASK + JINJA2)

## ROLE & CONTEXT
You are an Expert Frontend Engineer. We are upgrading the UI of an "AI Sales Intelligence" Flask application. 
The backend APIs are fully built. Your task is to write the Flask/Jinja2 templates, CSS, and JavaScript to match the layout and functional flow of a provided 8-screen mockup, while strictly adhering to our original brand color palette.

**Crucial Constraints:**
1.  **STRICT COLOR PALETTE:** Do NOT use the blue/gray from the mockup images. You MUST use our original Teal/Navy palette defined below.
2.  **FOCUS ON FUNCTIONALITY:** Do not overcomplicate. Build fewer features, but ensure every button, form, and API call actually works with proper loading states and error handling.
3.  **NO FRAMEWORKS:** Use plain HTML, Bootstrap 5 (via CDN), and Vanilla JavaScript. No React or Vue.

---

## 1. DESIGN SYSTEM & COLOR PALETTE
Strictly apply these colors via CSS variables:
```css
:root {
  --primary-teal: #00B4A0;       /* Main buttons, active states, highlights */
  --dark-navy: #1B264F;          /* Sidebar background, headings */
  --soft-mint: #E0F7FA;          /* Backgrounds for hero sections, badges */
  --bg-light: #F4F6F8;           /* Main app background */
  --text-dark: #1E293B;          /* Body text */
  --text-muted: #64748B;         /* Subtext, labels */
  --white: #FFFFFF;              /* Cards, panels */
  --danger: #EF4444;             /* Errors, Badges */
  --warning: #F59E0B;            /* Alerts, Badges */
  --success: #10B981;            /* Success, Badges */
}
```
- **Typography:** Google Font 'Inter' (Sans-serif).
- **Cards:** White background, `border-radius: 12px`, soft `box-shadow: 0 4px 6px rgba(0,0,0,0.05)`, no borders.
- **Badges:** Pill-shaped, soft background matching the color (e.g., light teal bg with dark teal text).

---

## 2. GLOBAL LAYOUT (`base.html`)
Create a layout that mimics the mockups:
- **Left Sidebar (Fixed, `width: 260px`, Dark Navy `--dark-navy`):**
  - Logo text at top ("AI Sales Intelligence" in white).
  - Nav Links (text white/muted, hover states in Teal): Dashboard, Companies, New Research, Research Reports, Opportunities, Proposals, My Business, Settings.
- **Top Navbar:**
  - Left: A dynamic breadcrumb/context pill (e.g., `From: Our Company → To: ABC Technologies`). Use `--soft-mint` background with `--text-dark`.
  - Right: User profile avatar and name dropdown.
- **Main Content Area:** Background `--bg-light`, padding `2rem`.

---

## 3. PAGE-BY-PAGE IMPLEMENTATION

### Page 1: Dashboard (`dashboard.html`)
- **Top Row (4 KPI Cards):** 
  - Total Companies, Research Completed, Pending, Proposals Ready.
  - Large numbers, small muted labels, and a small icon in a `--soft-mint` circle.
- **Middle Row:** 
  - Left (60%): "Research Activity" line chart. Use Chart.js via CDN. The line color must be `--primary-teal`.
  - Right (40%): "Needs your attention" list. 3 items with Company Name, action needed, and colored badges (Warning/Info/Danger).
- **Bottom Row:** "Top Opportunities" table. Columns: Opportunity Name, Priority (Badge), Evidence (Badge).

### Page 2: Companies (`companies.html`)
- **Header:** Title "Companies" + a `--primary-teal` "Add Company" button.
- **Filters:** A row of 3 inputs (Search, Industry Dropdown, Status Dropdown).
- **Table:** Clean white card. Columns: Company, Website, Industry, Status, Evaluator, Added. 
  - Use badges for Status and Evaluator (e.g., Success badge for "Approved", Warning for "Needs Revision").

### Page 3: New Research (`new_research.html`)
- **Layout:** A 3-column CSS Grid.
  - **Card 1 (Company Info):** Text inputs for Company Name, Website URL, Industry.
  - **Card 2 (Sources):** Checkboxes (Public reviews, Products, Market trends). A textarea for "LinkedIn: paste URL or text".
  - **Card 3 (Upload):** A dashed-border drag-and-drop zone.
- **Action Bar (Bottom):** "Save as Draft" (outline button) and "Start AI Research" (solid `--primary-teal` button).
- **JS Logic:** On "Start AI Research" click, disable the button, show a spinner, POST to the backend, then redirect to the Proposals page.

### Page 4: Proposals & Outreach (`proposal.html`)
- **Header Stepper:** A horizontal timeline: `1 AI Draft (done)` -> `2 Evaluator (Approved)` -> `3 Review (current)` -> `4 Send (locked)`. Use Teal for completed, Gray for pending.
- **Main Grid (2 columns):**
  - **Left (Proposal Text):** A large card containing the generated text. Next to key sentences, add badges like `Fact (Source 1)` or `Assumption`.
  - **Right (Evaluator Checks):** A card with a checklist. E.g., "Claims have sources [Pass]", "No exaggerated claims [Pass]". Use green checkmarks.
- **Action Bar (Bottom):** "Copy Email", "Download PDF", and "Mark as reviewed" (Teal button). 

### Page 5: My Business / Services (`profile.html`)
- **Grid Layout (2 columns):**
  - **Left (Company Profile):** Form inputs for Name, Industry, Value Proposition. "Save Profile" button.
  - **Right (Service Catalog):** A dynamic table of services. "Add Service" button opens a Bootstrap modal to append a new row.

---

## 4. JAVASCRIPT & INTERACTIVITY (`static/js/main.js`)
1.  **AOS Animations:** Initialize `AOS.init()` in `base.html`. Add `data-aos="fade-up"` to cards.
2.  **Loading States:** Create a helper function `toggleBtn(btnId, isLoading)`. When loading, change text to "Processing..." and add a CSS spinner.
3.  **Toasts:** Use SweetAlert2 (via CDN) for all success/error messages. Example:
    ```javascript
    Swal.fire({ title: 'Success!', text: 'Company added.', icon: 'success', confirmButtonColor: '#00B4A0' });
    ```
4.  **API Calls:** Use `fetch()`. Handle responses and errors gracefully.

## EXECUTION INSTRUCTIONS FOR AI AGENT
1. Write `base.html` with the CDN links (Bootstrap, Chart.js, SweetAlert2, AOS, Google Fonts).
2. Write `style.css` enforcing the Navy/Teal palette on Bootstrap components.
3. Build `dashboard.html` and `companies.html` with mock data first to verify layout.
4. Build `new_research.html` and `proposal.html`.
5. Provide the complete `main.js` to handle form submissions and button clicks.
