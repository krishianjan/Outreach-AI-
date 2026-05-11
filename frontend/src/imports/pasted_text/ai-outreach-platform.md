Build a complete, highly polished single-page web application called "AI Outreach Platform" 
using React + Tailwind CSS only. No backend — all API calls go to a FastAPI backend 
at http://localhost:7860. Use fetch() for all requests.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DESIGN SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Color palette (use CSS variables):
  --bg-primary:     #050810   (near-black, main background)
  --bg-card:        #0D1117   (card backgrounds)
  --bg-elevated:    #161B22   (inputs, hover states)
  --border:         #21262D   (all borders)
  --accent-purple:  #7C3AED   (primary CTA buttons)
  --accent-emerald: #10B981   (success states, verified badges)
  --accent-amber:   #F59E0B   (warnings, Hunter budget bar)
  --accent-blue:    #3B82F6   (info, links)
  --accent-pink:    #EC4899   (reply rate, special stats)
  --text-primary:   #F0F6FC   (headings, labels)
  --text-secondary: #8B949E   (body text, descriptions)
  --text-muted:     #484F58   (placeholders, disabled)
  --gradient-hero:  linear-gradient(135deg, #7C3AED 0%, #3B82F6 50%, #10B981 100%)

Typography: Inter font (import from Google Fonts)
Border radius: 12px cards, 8px inputs, 6px badges
Transitions: all 0.2s ease on hover states
Shadows: 0 0 0 1px var(--border), 0 4px 24px rgba(0,0,0,0.4) for cards

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LAYOUT STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Fixed top navbar + tab-based main content area. No page routing needed.

NAVBAR (fixed, height 56px, blur backdrop):
  Left:  Logo — gradient text "⚡ Outreach AI" (bold, 18px)
  Center: Tab navigation — Dashboard | Outreach | Pipeline | Settings
  Right: Mode badge (green dot "LIVE" or amber dot "DRY RUN") + 
         small stat "8 credits left" in muted text

TABS render below navbar. Active tab underline uses --accent-purple.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TAB 1: DASHBOARD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

On mount: GET /api/stats → populate all cards. Auto-refresh every 30s.

Layout: full width, max-width 1100px centered, padding 32px

Row 1 — 3 stat cards side by side:
  Each card: dark bg, subtle border, centered content
  - "Domains Cached"  value in --accent-purple, large (36px bold)
  - "Contacts Found"  value in --accent-emerald
  - "Active Leads"    value in --accent-blue

Row 2 — 3 smaller stat cards:
  - "Emails Sent"     --accent-amber
  - "Replies"         --accent-emerald  
  - "Reply Rate"      --accent-pink, formatted as "12.5%"

Row 3 — 2 API budget progress bars side by side:
  Left:  "🎯 Hunter Credits" — amber fill bar, shows "3 / 8 today"
  Right: "🤖 Gemini Calls"  — emerald fill bar, shows "45 / 200 today"
  Bars: 6px height, rounded, animated fill on load (CSS transition width)

Row 4 — Recent activity feed (last 5 actions from GET /api/activity):
  Each row: left icon, "stripe.com → 3 contacts found", right "2 min ago"
  Subtle left border in the relevant accent color per action type

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TAB 2: OUTREACH  (most important tab)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Two-column layout (left 420px fixed, right fills remaining space)

─── LEFT PANEL: "Find Contacts" ───────────────────────

Label at top: "STEP 1" in small caps, --accent-purple

Input 1 — Company Name (large, prominent):
  Placeholder: "e.g. Stripe, OpenAI, Cardinal AI"
  Below input: small muted text "We'll find the domain automatically"
  This sends company name to POST /api/find-domain which returns domain

Input 2 — Outreach Purpose dropdown:
  Options with emoji (display label → internal value passed to API):
    "💼 Founding Engineer Role"        → job_seeker
    "🚀 Startup Collaboration"         → startup_founder
    "💰 Investor Pitch"                → investor_pitch
    "🤝 Referral Request"              → referral_request
    "📈 B2B Sales"                     → b2b_sales
    "📨 Cold Outreach"                 → cold_outreach
    "🔗 Partnership"                   → partnership
  Custom styled select, not browser default

Big CTA button: "🔍 Find Contacts"
  Full width, gradient bg (purple→blue), 48px height, bold text
  Loading state: spinner + "Finding contacts..." text, button disabled

On click → POST /api/lookup with { company_name, domain (if found), purpose }

Loading skeleton (show while waiting):
  3 placeholder contact rows with shimmer animation

Contact Results (appear after API response):
  Source badge top-right: "via Hunter" / "via Scraper" / "cached" 
  (use colored badge, NOT text "via Hunter" — just icon + source name)
  
  Each contact card (max 8):
    Left: avatar circle with first initial, gradient bg
    Center: Name (bold), Role (muted), Email (purple monospace)
    Right: Verify grade badge — 🟢 HIGH / 🟡 MEDIUM / 🔴 LOW
           Small copy icon button next to email — copies email to clipboard
           On copy: brief "Copied!" tooltip fade in/out

  Click a contact → selects it (highlighted border) → populates Step 2

─── RIGHT PANEL: "Generate Email" ─────────────────────

Label: "STEP 2" in small caps, --accent-emerald

Selected contact display (shows after selection):
  Card with avatar, name, role, email, grade badge
  "Change" link to go back to contact list

Your Details section (collapsed accordion by default, label "👤 Your Details"):
  Fields: Your Name, Your Title, Your Company, LinkedIn URL
  IMPORTANT: These fields adapt their label based on purpose:
    - job_seeker: "Your Background / Key Skills"
    - investor_pitch: "Your Fund / Portfolio"  
    - b2b_sales: "Your Product / Value Prop"
    - default: "Your Company"
  Store these in localStorage so user doesn't retype every time

Model Selection (small segmented control, right-aligned):
  [Gemini Flash] [Groq] [Auto]
  Auto = model_router decides (default)
  This sets a "preferred_model" param in the API call
  Show small tooltip on each: "Fast & free (1500/day)" etc.

Follow-up toggle: "📧 This is a follow-up" checkbox
  When checked: textarea appears "Paste your previous email"

Generate button: "✨ Generate Full Campaign"
  Full width, gradient, 48px
  Loading: animated gradient shimmer on button + "Writing your emails..."

─── EMAIL OUTPUT AREA (appears below or replaces loading) ───

This is the most important UI section. Make it feel like a real email editor.

Tabbed output: [Day 0 — Primary] [Day 3 — Follow-up] [Day 7 — Bump] [Day 14 — Close]
Active tab underline. All 4 tabs pre-generated.

Each tab shows:
  Subject line section:
    Label "Subject Line" (small caps, muted)
    3 clickable subject variants as pills:
      Pill style: dark bg, border, hover highlights in purple
      Clicking a pill selects it (purple border) and copies it to clipboard
      Selected pill has purple background
    
  Email body:
    Large textarea (min 200px, auto-grows), dark bg, white text
    Fully editable — user can type directly in here
    Top-right corner of textarea: small "Copy ✓" button
    
    IMPORTANT: The body must be a COMPLETE professional email, not a summary.
    Full greeting, full paragraphs, proper sign-off with sender's name.
    Example format the API returns and must display correctly:
    
    "Hi [Name],
    
    I noticed [Company] recently [specific detail] — that caught my attention 
    because [specific reason relevant to sender's background].
    
    I'm [Name], [Title] at [Company]. [1-2 sentences of specific value/proof].
    [Clear ask — 15-min call this week?]
    
    Best,
    [Sender Name]
    [Title] | [Company]
    [LinkedIn URL]"
    
  P.S. line (if present):
    Separate subtle box below textarea, italic text, copyable
    
  Action bar below email:
    [📋 Copy Full Email] [✏️ Reset to Original] [📤 Mark as Sent]
    Copy button: copies subject + body together, shows "Copied!" confirmation
    Reset: restores AI-generated text (before user edits)
    Mark as Sent: PATCH /api/leads/{id}/status with { status: "sent" }

AI suggestion strip (below action bar):
  Small subtle box: "💡 AI Suggestion: Subject line 2 has 34% higher open rate for {purpose} outreach"
  This is static/hardcoded per purpose for now, not a real API call

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TAB 3: PIPELINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GET /api/leads on mount → populate table

Clean table (not a spreadsheet):
  Columns: Status | Contact | Company | Purpose | Last Action | Actions
  
  Status column: colored pill badges
    🔍 Discovered (gray)
    ✅ Verified (emerald)  
    📝 Drafted (blue)
    📤 Sent (amber)
    👁 Opened (purple)
    💬 Replied (pink)
    📅 Booked (emerald, bold)
    ⏭ Skipped (muted)

  Each row Actions column: 
    [View Email] [Change Status ▾] [Copy Email]
    Change Status is a small dropdown

  Empty state (no leads): 
    Centered illustration placeholder, text "No leads yet. 
    Start by finding contacts in the Outreach tab."

  Filter bar above table:
    Status filter pills (All | Sent | Replied | Booked)
    Search input for email/domain

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TAB 4: SETTINGS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Two columns:

Left — Configuration Status cards:
  Each API: name, configured/not badge, small description
  Hunter, Gemini, Groq, ScrapingGraph
  
Right — Usage limits:
  Same progress bars as dashboard but with edit inputs
  "Daily Hunter Limit" number input → POST /api/settings
  
Sender Profile section (persisted to localStorage):
  Form: Name, Title, Company, LinkedIn, Background blurb
  "Save Profile" button → saves to localStorage
  Auto-populates the Step 2 fields when returning
  
Danger zone (bottom, subtle red border):
  "Clear Database" button with confirmation dialog
  "Export Leads CSV" button → GET /api/export/csv

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API ENDPOINTS TO CALL (exact paths, match backend)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GET  /api/stats                          → dashboard numbers
GET  /api/activity                       → recent activity feed
POST /api/find-domain                    → { company_name } → { domain, confidence }
POST /api/lookup                         → { company_name, domain, purpose } → { contacts[], source, error }
POST /api/generate                       → { email, domain, purpose, sender, preferred_model, is_followup, previous_email }
                                           → { day_0:{subject,subject_variants[],body,ps_line}, day_3, day_7, day_14, model_used }
GET  /api/leads                          → [{ id, email, domain, status, purpose, first_name, last_name }]
PATCH /api/leads/{id}/status             → { status }
POST /api/settings                       → { hunter_daily_limit, gemini_daily_limit }
GET  /api/export/csv                     → CSV file download

All requests: Content-Type: application/json
All responses include: { success: bool, error: string | null }
On error: show inline error toast (bottom-right, auto-dismiss 4s, red border)
On success actions: show success toast (green border)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LOADING + MICRO-INTERACTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Contact search loading:
  Button becomes disabled with spinner
  Below button: animated 3-row skeleton (shimmer effect, dark bg)
  
Email generation loading:
  Button: animated gradient sweep left-to-right (keyframe animation)
  Text cycles: "Researching company..." → "Writing Day 0..." → "Writing follow-ups..."
  Each message shows for 2 seconds using setInterval
  Output area shows blurred placeholder text while loading

Copy interactions:
  On any copy button: icon changes to checkmark for 1.5s then back
  Brief scale(1.05) pulse animation on the copied element

Tab switching:
  Fade in (opacity 0 → 1, translateY 4px → 0, 150ms)

Toast notifications (bottom-right stack):
  Slide in from right, auto-dismiss 4s
  Max 3 visible at once, older ones slide out

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMPONENT STATE RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Global state (React useState or Zustand):
  - selectedContact: null | Contact object
  - currentDomain: string
  - generatedSequence: null | { day_0, day_3, day_7, day_14, model_used }
  - editedBodies: { day_0: string, day_3: string, day_7: string, day_14: string }
  - senderProfile: { name, title, company, linkedin, background } (from localStorage)
  - preferredModel: "auto" | "gemini_flash" | "groq"
  - activeTab: "dashboard" | "outreach" | "pipeline" | "settings"

editedBodies: starts as copy of generatedSequence bodies.
  User edits go into editedBodies, not generatedSequence.
  "Reset to Original" copies generatedSequence back into editedBodies.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT NOT TO BUILD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- No authentication / login screens
- No payment flows  
- No "via Hunter" text anywhere in contact results UI
- No browser-default styled selects or checkboxes (custom style everything)
- No lorem ipsum placeholder content
- No multi-page routing (single page, tabs only)
- No external UI libraries (Tailwind only, no MUI, no Ant Design, no Chakra)
- Do not show raw API keys anywhere in the UI

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE OUTPUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Output exactly these files:
  src/App.jsx              — root with tab state
  src/components/Navbar.jsx
  src/components/Dashboard.jsx
  src/components/Outreach.jsx   — the main tab (largest file)
  src/components/Pipeline.jsx
  src/components/Settings.jsx
  src/components/EmailEditor.jsx — the Day 0/3/7/14 tabbed editor
  src/components/ContactCard.jsx — single contact display
  src/components/Toast.jsx       — notification system
  src/hooks/useOutreach.js       — all fetch() API calls in one file
  src/hooks/useLocalStorage.js   — sender profile persistence
  src/constants/purposes.js      — PURPOSE_CHOICES array (label + value pairs)
  src/index.css                  — CSS variables + global styles + animations
  index.html                     — script tag pointing to src/main.jsx
  
Variable names that MUST match the backend exactly:
  purpose values: job_seeker | startup_founder | investor_pitch | referral_request | b2b_sales | cold_outreach | partnership
  contact fields: value (email), first_name, last_name, position, verify_grade
  sequence fields: day_0, day_3, day_7, day_14 (each has subject, subject_variants, body, ps_line)
  lead status values: discovered | verified | drafted | sent | opened | replied | booked | skipped
  model values: gemini_flash | groq | auto