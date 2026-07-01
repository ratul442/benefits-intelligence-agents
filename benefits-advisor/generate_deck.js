/**
 * Benefits Benchmarking — Hosted Agents Protocol Comparison Deck
 * 
 * Generates a PowerPoint explaining:
 * - What hosted agents are
 * - Invocations vs Responses protocols
 * - Where Foundry Toolbox and Skills are used
 * - Architecture of the Responses demo
 * - How to run the demo end to end
 */

const pptxgen = require("pptxgenjs");

// --- Color Palette: Ocean Gradient (professional, trust-oriented) ---
const COLORS = {
  primary: "065A82",      // Deep blue
  secondary: "1C7293",    // Teal
  accent: "21295C",       // Midnight
  light: "E8F4F8",        // Ice
  white: "FFFFFF",
  dark: "1A1A2E",         // Near-black
  gray: "6B7280",         // Mid gray
  lightGray: "F3F4F6",    // Light bg
  green: "10B981",        // Success
  orange: "F59E0B",       // Warning
  purple: "7C3AED",       // Highlight
};

const FONT = { heading: "Calibri", body: "Calibri Light" };

function addTitleSlide(pres) {
  let slide = pres.addSlide();
  slide.background = { color: COLORS.dark };

  // Large title
  slide.addText("Hosted Agents:\nInvocations vs Responses", {
    x: 0.8, y: 1.2, w: 8.4, h: 2.2,
    fontSize: 40, fontFace: FONT.heading, color: COLORS.white, bold: true,
    lineSpacingMultiple: 1.2,
  });

  // Subtitle
  slide.addText("Protocol Comparison & Live Demo", {
    x: 0.8, y: 3.5, w: 8.4, h: 0.6,
    fontSize: 22, fontFace: FONT.body, color: COLORS.secondary,
  });

  // Footer
  slide.addText("Benefits Benchmarking | Azure AI Foundry | May 2026", {
    x: 0.8, y: 4.8, w: 8.4, h: 0.4,
    fontSize: 12, fontFace: FONT.body, color: COLORS.gray,
  });

  // Accent bar
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.8, y: 3.3, w: 2.5, h: 0.06, fill: { color: COLORS.secondary },
  });
}

function addAgendaSlide(pres) {
  let slide = pres.addSlide();
  slide.background = { color: COLORS.white };

  slide.addText("Agenda", {
    x: 0.8, y: 0.4, w: 8.4, h: 0.8,
    fontSize: 32, fontFace: FONT.heading, color: COLORS.accent, bold: true,
  });

  const items = [
    "What are Hosted Agents?",
    "The Invocations Protocol",
    "The Responses Protocol",
    "Key Differences",
    "Foundry Toolbox & Skills",
    "Demo Architecture",
    "Live Demo Walkthrough",
    "When to Use Which Protocol",
  ];

  slide.addText(
    items.map((item, i) => ({
      text: `${i + 1}.  ${item}`,
      options: { breakLine: true, fontSize: 16, color: COLORS.dark },
    })),
    { x: 1.2, y: 1.5, w: 7.5, h: 3.8, fontFace: FONT.body, lineSpacingMultiple: 1.8 }
  );
}

function addWhatAreHostedAgents(pres) {
  let slide = pres.addSlide();
  slide.background = { color: COLORS.white };

  slide.addText("What are Hosted Agents?", {
    x: 0.8, y: 0.4, w: 8.4, h: 0.7,
    fontSize: 28, fontFace: FONT.heading, color: COLORS.accent, bold: true,
  });

  // Definition box
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.8, y: 1.3, w: 8.4, h: 1.2,
    fill: { color: COLORS.light }, rectRadius: 0.05,
  });
  slide.addText(
    "Custom containers running your agent code, hosted by Azure AI Foundry.\n" +
    "You bring the logic — Foundry provides hosting, scaling, identity, and observability.",
    {
      x: 1.1, y: 1.4, w: 7.8, h: 1.0,
      fontSize: 14, fontFace: FONT.body, color: COLORS.dark, valign: "middle",
    }
  );

  // Key features in 3 columns
  const features = [
    { title: "Container-Based", desc: "Docker image with\nyour Python code" },
    { title: "Managed Infra", desc: "Auto-scaling, identity,\nnetworking by Foundry" },
    { title: "Protocol Choice", desc: "Invocations OR\nResponses protocol" },
  ];

  features.forEach((f, i) => {
    const x = 0.8 + i * 3.1;
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.8, w: 2.8, h: 2.2,
      fill: { color: COLORS.lightGray },
      shadow: { type: "outer", color: "000000", blur: 4, offset: 2, angle: 135, opacity: 0.08 },
    });
    slide.addText(f.title, {
      x, y: 2.9, w: 2.8, h: 0.5,
      fontSize: 14, fontFace: FONT.heading, color: COLORS.primary, bold: true, align: "center",
    });
    slide.addText(f.desc, {
      x, y: 3.4, w: 2.8, h: 1.4,
      fontSize: 12, fontFace: FONT.body, color: COLORS.dark, align: "center", valign: "middle",
    });
  });
}

function addInvocationsProtocol(pres) {
  let slide = pres.addSlide();
  slide.background = { color: COLORS.white };

  slide.addText("The Invocations Protocol", {
    x: 0.8, y: 0.4, w: 8.4, h: 0.7,
    fontSize: 28, fontFace: FONT.heading, color: COLORS.accent, bold: true,
  });

  slide.addText("Used by: Benefits Review Agent (../benefits-review)", {
    x: 0.8, y: 1.0, w: 8.4, h: 0.4,
    fontSize: 12, fontFace: FONT.body, color: COLORS.gray, italic: true,
  });

  // Flow diagram as text
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.8, y: 1.6, w: 8.4, h: 1.4,
    fill: { color: COLORS.light },
  });
  slide.addText(
    "BOL Backend  →  POST /invocations  →  Your Pipeline  →  SSE Response\n" +
    "(Structured JSON)     (Fire & Forget)      (You control)     (Structured JSON)",
    {
      x: 1.0, y: 1.7, w: 8.0, h: 1.2,
      fontSize: 13, fontFace: "Consolas", color: COLORS.dark, valign: "middle",
      lineSpacingMultiple: 1.6,
    }
  );

  // Characteristics
  const chars = [
    "Single request → single response (no conversation)",
    "YOU control the orchestration (topic slicing, parallel LLM calls, alignment)",
    "Structured input: company_payload + market_payload + catalog",
    "Output: deterministic JSON with 160 validated report rows",
    "No model-directed tool use — pipeline is hardcoded",
    "Ideal for: batch processing, API-to-API, deterministic pipelines",
  ];

  slide.addText(
    chars.map(c => ({ text: c, options: { bullet: true, breakLine: true } })),
    { x: 1.0, y: 3.2, w: 8.0, h: 2.2, fontSize: 13, fontFace: FONT.body, color: COLORS.dark, lineSpacingMultiple: 1.4 }
  );
}

function addResponsesProtocol(pres) {
  let slide = pres.addSlide();
  slide.background = { color: COLORS.white };

  slide.addText("The Responses Protocol", {
    x: 0.8, y: 0.4, w: 8.4, h: 0.7,
    fontSize: 28, fontFace: FONT.heading, color: COLORS.accent, bold: true,
  });

  slide.addText("Used by: Benefits Cost Advisor (benefits-advisor)", {
    x: 0.8, y: 1.0, w: 8.4, h: 0.4,
    fontSize: 12, fontFace: FONT.body, color: COLORS.gray, italic: true,
  });

  // Flow diagram
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.8, y: 1.6, w: 8.4, h: 1.4,
    fill: { color: COLORS.light },
  });
  slide.addText(
    "User  ↔  POST /responses  ↔  Agent (Model decides)  ↔  Tools + Skills\n" +
    "(Natural language)   (Multi-turn)     (Model-directed)      (On-demand)",
    {
      x: 1.0, y: 1.7, w: 8.0, h: 1.2,
      fontSize: 13, fontFace: "Consolas", color: COLORS.dark, valign: "middle",
      lineSpacingMultiple: 1.6,
    }
  );

  // Characteristics
  const chars = [
    "Multi-turn conversation with session history",
    "MODEL controls the flow — decides when to search, compute, or load skills",
    "Natural language input: ask questions, follow up, iterate",
    "Token-by-token streaming (OpenAI Responses API compatible)",
    "Model-directed tool use via Foundry Toolbox (MCP protocol)",
    "Ideal for: interactive advisory, research, exploratory analysis",
  ];

  slide.addText(
    chars.map(c => ({ text: c, options: { bullet: true, breakLine: true } })),
    { x: 1.0, y: 3.2, w: 8.0, h: 2.2, fontSize: 13, fontFace: FONT.body, color: COLORS.dark, lineSpacingMultiple: 1.4 }
  );
}

function addKeyDifferences(pres) {
  let slide = pres.addSlide();
  slide.background = { color: COLORS.white };

  slide.addText("Key Differences", {
    x: 0.8, y: 0.3, w: 8.4, h: 0.6,
    fontSize: 28, fontFace: FONT.heading, color: COLORS.accent, bold: true,
  });

  const tableData = [
    [
      { text: "Dimension", options: { bold: true, color: "FFFFFF", fill: { color: COLORS.primary } } },
      { text: "Invocations", options: { bold: true, color: "FFFFFF", fill: { color: COLORS.primary } } },
      { text: "Responses", options: { bold: true, color: "FFFFFF", fill: { color: COLORS.primary } } },
    ],
    ["Interaction", "Fire-and-forget", "Multi-turn conversation"],
    ["Input", "Structured JSON", "Natural language"],
    ["Tool Use", "Hardcoded pipeline", "Model-directed (runtime)"],
    ["Streaming", "Custom SSE events", "OpenAI-compatible tokens"],
    ["State", "Stateless", "Session history"],
    ["Orchestration", "Developer controls", "Model controls"],
    ["Best For", "Batch / deterministic", "Interactive / advisory"],
  ];

  slide.addTable(tableData, {
    x: 0.8, y: 1.1, w: 8.4, h: 4.2,
    fontSize: 12, fontFace: FONT.body, color: COLORS.dark,
    border: { type: "solid", pt: 0.5, color: "CCCCCC" },
    rowH: [0.45, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
    colW: [2.0, 3.2, 3.2],
    align: "left", valign: "middle",
  });
}

function addToolboxSlide(pres) {
  let slide = pres.addSlide();
  slide.background = { color: COLORS.white };

  slide.addText("Foundry Toolbox", {
    x: 0.8, y: 0.4, w: 8.4, h: 0.7,
    fontSize: 28, fontFace: FONT.heading, color: COLORS.accent, bold: true,
  });

  slide.addText("Managed tool registry — define tools centrally, share across agents", {
    x: 0.8, y: 1.0, w: 8.4, h: 0.4,
    fontSize: 14, fontFace: FONT.body, color: COLORS.gray,
  });

  // Two tool cards
  const tools = [
    {
      name: "web_search",
      desc: "Real-time market research:\n• Latest Singapore benefits trends\n• Regulatory updates (MOM, CPF)\n• Competitor practices\n• Salary survey data",
      color: COLORS.primary,
    },
    {
      name: "code_interpreter",
      desc: "On-the-fly calculations:\n• Cost projections with inflation\n• Benchmarking vs P25/P50/P75\n• What-if scenario modeling\n• Statistical analysis",
      color: COLORS.secondary,
    },
  ];

  tools.forEach((tool, i) => {
    const x = 0.8 + i * 4.5;
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.7, w: 4.0, h: 3.2,
      fill: { color: COLORS.lightGray },
      shadow: { type: "outer", color: "000000", blur: 4, offset: 2, angle: 135, opacity: 0.08 },
    });
    // Tool name header
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.7, w: 4.0, h: 0.5,
      fill: { color: tool.color },
    });
    slide.addText(tool.name, {
      x, y: 1.7, w: 4.0, h: 0.5,
      fontSize: 14, fontFace: "Consolas", color: COLORS.white, bold: true,
      align: "center", valign: "middle",
    });
    slide.addText(tool.desc, {
      x: x + 0.2, y: 2.4, w: 3.6, h: 2.3,
      fontSize: 12, fontFace: FONT.body, color: COLORS.dark, lineSpacingMultiple: 1.4,
    });
  });

  // How it connects
  slide.addText("Connection: Agent → MCPStreamableHTTPTool → Toolbox MCP endpoint (auto-discovered at runtime)", {
    x: 0.8, y: 5.1, w: 8.4, h: 0.4,
    fontSize: 11, fontFace: "Consolas", color: COLORS.gray,
  });
}

function addSkillsSlide(pres) {
  let slide = pres.addSlide();
  slide.background = { color: COLORS.white };

  slide.addText("Foundry Skills", {
    x: 0.8, y: 0.4, w: 8.4, h: 0.7,
    fontSize: 28, fontFace: FONT.heading, color: COLORS.accent, bold: true,
  });

  slide.addText("Behavioral guidelines decoupled from code — update without redeploying", {
    x: 0.8, y: 1.0, w: 8.4, h: 0.4,
    fontSize: 14, fontFace: FONT.body, color: COLORS.gray,
  });

  // Two skill cards
  const skills = [
    {
      name: "cost-analysis-methodology",
      desc: "5-step framework:\n1. Cost Decomposition\n2. Per-Employee Normalization\n3. Market Positioning (P25–P75)\n4. Cost Driver Analysis\n5. Optimization Recommendations",
      trigger: "\"benchmark costs\", \"optimize benefits\"",
    },
    {
      name: "regulatory-guidance-sgp",
      desc: "Singapore regulations:\n• CPF contribution rates & ceilings\n• Employment Act leave minimums\n• WICA requirements\n• MOM tripartite standards\n• Optimization constraints",
      trigger: "\"CPF\", \"statutory\", \"compliance\"",
    },
  ];

  skills.forEach((skill, i) => {
    const x = 0.8 + i * 4.5;
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.7, w: 4.0, h: 3.0,
      fill: { color: COLORS.lightGray },
      shadow: { type: "outer", color: "000000", blur: 4, offset: 2, angle: 135, opacity: 0.08 },
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.7, w: 4.0, h: 0.5,
      fill: { color: COLORS.purple },
    });
    slide.addText(skill.name, {
      x, y: 1.7, w: 4.0, h: 0.5,
      fontSize: 12, fontFace: "Consolas", color: COLORS.white, bold: true,
      align: "center", valign: "middle",
    });
    slide.addText(skill.desc, {
      x: x + 0.2, y: 2.4, w: 3.6, h: 2.0,
      fontSize: 11, fontFace: FONT.body, color: COLORS.dark, lineSpacingMultiple: 1.3,
    });
    slide.addText(`Triggered by: ${skill.trigger}`, {
      x: x + 0.2, y: 4.3, w: 3.6, h: 0.3,
      fontSize: 10, fontFace: FONT.body, color: COLORS.gray, italic: true,
    });
  });

  // Progressive disclosure explanation
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.8, y: 4.9, w: 8.4, h: 0.6,
    fill: { color: COLORS.light },
  });
  slide.addText(
    "Progressive Disclosure: Skill names advertised → Model calls load_skill when relevant → Full content injected (saves tokens)",
    {
      x: 1.0, y: 4.95, w: 8.0, h: 0.5,
      fontSize: 11, fontFace: FONT.body, color: COLORS.dark, valign: "middle",
    }
  );
}

function addArchitectureSlide(pres) {
  let slide = pres.addSlide();
  slide.background = { color: COLORS.white };

  slide.addText("Demo Architecture", {
    x: 0.8, y: 0.3, w: 8.4, h: 0.6,
    fontSize: 28, fontFace: FONT.heading, color: COLORS.accent, bold: true,
  });

  // Architecture diagram as structured text
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.0, w: 9.0, h: 4.3,
    fill: { color: COLORS.lightGray },
  });

  // Container box
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.8, y: 1.2, w: 5.5, h: 3.9,
    fill: { color: COLORS.white },
    line: { color: COLORS.primary, width: 2, dashType: "dash" },
  });
  slide.addText("Hosted Agent Container", {
    x: 0.9, y: 1.3, w: 3.0, h: 0.3,
    fontSize: 10, fontFace: FONT.body, color: COLORS.primary, bold: true,
  });

  // Main.py box
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 1.2, y: 1.8, w: 4.8, h: 1.0,
    fill: { color: COLORS.light },
  });
  slide.addText("main.py — ResponsesHostServer", {
    x: 1.3, y: 1.85, w: 4.6, h: 0.35,
    fontSize: 11, fontFace: "Consolas", color: COLORS.dark, bold: true,
  });
  slide.addText("POST /responses ← Multi-turn conversation", {
    x: 1.3, y: 2.2, w: 4.6, h: 0.35,
    fontSize: 10, fontFace: FONT.body, color: COLORS.gray,
  });

  // Agent box
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 1.2, y: 3.0, w: 4.8, h: 0.8,
    fill: { color: COLORS.light },
  });
  slide.addText("Agent(client=FoundryChatClient, tools=[Toolbox], context_providers=[Skills])", {
    x: 1.3, y: 3.1, w: 4.6, h: 0.6,
    fontSize: 10, fontFace: "Consolas", color: COLORS.dark, valign: "middle",
  });

  // Skills box
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 1.2, y: 4.0, w: 2.2, h: 0.9,
    fill: { color: "EDE9FE" },
  });
  slide.addText("Skills\n(downloaded)\ncost-analysis\nregulatory-sgp", {
    x: 1.3, y: 4.0, w: 2.0, h: 0.9,
    fontSize: 9, fontFace: FONT.body, color: COLORS.purple, valign: "middle",
  });

  // External services
  // Model
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 6.8, y: 1.3, w: 2.4, h: 0.8,
    fill: { color: COLORS.primary },
  });
  slide.addText("GPT-4.1-mini\n(Model)", {
    x: 6.8, y: 1.3, w: 2.4, h: 0.8,
    fontSize: 11, fontFace: FONT.body, color: COLORS.white, align: "center", valign: "middle",
  });

  // Toolbox
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 6.8, y: 2.4, w: 2.4, h: 1.2,
    fill: { color: COLORS.secondary },
  });
  slide.addText("Foundry Toolbox\n(MCP)\n• web_search\n• code_interpreter", {
    x: 6.8, y: 2.4, w: 2.4, h: 1.2,
    fontSize: 10, fontFace: FONT.body, color: COLORS.white, align: "center", valign: "middle",
  });

  // Skills API
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 6.8, y: 3.9, w: 2.4, h: 0.8,
    fill: { color: COLORS.purple },
  });
  slide.addText("Foundry Skills API\n(beta.skills)", {
    x: 6.8, y: 3.9, w: 2.4, h: 0.8,
    fontSize: 10, fontFace: FONT.body, color: COLORS.white, align: "center", valign: "middle",
  });
}

function addDemoWalkthrough(pres) {
  let slide = pres.addSlide();
  slide.background = { color: COLORS.white };

  slide.addText("Demo Walkthrough", {
    x: 0.8, y: 0.4, w: 8.4, h: 0.7,
    fontSize: 28, fontFace: FONT.heading, color: COLORS.accent, bold: true,
  });

  const steps = [
    { step: "1", title: "Provision Skills", desc: "python provision_skills.py → uploads SKILL.md files to Foundry", what: "Skills" },
    { step: "2", title: "Start Agent", desc: "python main.py → downloads skills, connects toolbox, starts server", what: "Startup" },
    { step: "3", title: "Ask Cost Question", desc: "\"Calculate total benefits cost for 500 employees...\" → code_interpreter", what: "Toolbox" },
    { step: "4", title: "Ask Regulatory Question", desc: "\"What are CPF rates?\" → loads regulatory-guidance-sgp skill", what: "Skills" },
    { step: "5", title: "Multi-Turn Follow-up", desc: "\"Now project 3 years with inflation\" → maintains context + computes", what: "Protocol" },
    { step: "6", title: "Market Research", desc: "\"Search latest Singapore benefits trends\" → web_search", what: "Toolbox" },
  ];

  steps.forEach((s, i) => {
    const y = 1.3 + i * 0.7;
    // Step number circle
    slide.addShape(pres.shapes.OVAL, {
      x: 0.8, y: y, w: 0.4, h: 0.4,
      fill: { color: COLORS.primary },
    });
    slide.addText(s.step, {
      x: 0.8, y: y, w: 0.4, h: 0.4,
      fontSize: 11, fontFace: FONT.heading, color: COLORS.white, align: "center", valign: "middle", bold: true,
    });
    // Title
    slide.addText(s.title, {
      x: 1.4, y: y, w: 2.0, h: 0.4,
      fontSize: 13, fontFace: FONT.heading, color: COLORS.dark, bold: true, valign: "middle",
    });
    // Description
    slide.addText(s.desc, {
      x: 3.4, y: y, w: 5.0, h: 0.4,
      fontSize: 11, fontFace: FONT.body, color: COLORS.gray, valign: "middle",
    });
    // Badge
    slide.addText(s.what, {
      x: 8.6, y: y + 0.05, w: 0.8, h: 0.3,
      fontSize: 9, fontFace: FONT.body, color: COLORS.white, align: "center", valign: "middle",
      fill: { color: s.what === "Toolbox" ? COLORS.secondary : s.what === "Skills" ? COLORS.purple : COLORS.primary },
    });
  });
}

function addRunInstructions(pres) {
  let slide = pres.addSlide();
  slide.background = { color: COLORS.dark };

  slide.addText("Running the Demo", {
    x: 0.8, y: 0.4, w: 8.4, h: 0.7,
    fontSize: 28, fontFace: FONT.heading, color: COLORS.white, bold: true,
  });

  const code = `# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure .env (copy from .env.example)
cp .env.example .env

# 3. Provision skills to Foundry (one time)
python provision_skills.py

# 4. Start the agent
python main.py

# 5. Test (in another terminal)
curl -X POST http://localhost:8088/responses \\
  -H "Content-Type: application/json" \\
  -d '{"input": "What tools do you have?"}'

# 6. Run full test suite
python test_local.py`;

  slide.addText(code, {
    x: 0.8, y: 1.3, w: 8.4, h: 4.0,
    fontSize: 11, fontFace: "Consolas", color: COLORS.green,
    lineSpacingMultiple: 1.3, valign: "top",
  });
}

function addWhenToUseWhich(pres) {
  let slide = pres.addSlide();
  slide.background = { color: COLORS.white };

  slide.addText("When to Use Which Protocol", {
    x: 0.8, y: 0.4, w: 8.4, h: 0.7,
    fontSize: 28, fontFace: FONT.heading, color: COLORS.accent, bold: true,
  });

  // Invocations column
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.8, y: 1.3, w: 4.0, h: 0.5,
    fill: { color: COLORS.primary },
  });
  slide.addText("Use INVOCATIONS when...", {
    x: 0.8, y: 1.3, w: 4.0, h: 0.5,
    fontSize: 13, fontFace: FONT.heading, color: COLORS.white, align: "center", valign: "middle", bold: true,
  });

  const invocations = [
    "Structured API-to-API integration",
    "Deterministic, repeatable outputs",
    "Batch processing (no user interaction)",
    "Custom orchestration (topic slicing)",
    "Output must be machine-parseable JSON",
    "You need full control over the pipeline",
  ];

  slide.addText(
    invocations.map(i => ({ text: i, options: { bullet: true, breakLine: true } })),
    { x: 0.9, y: 1.9, w: 3.8, h: 3.0, fontSize: 12, fontFace: FONT.body, color: COLORS.dark, lineSpacingMultiple: 1.5 }
  );

  // Responses column
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.2, y: 1.3, w: 4.0, h: 0.5,
    fill: { color: COLORS.secondary },
  });
  slide.addText("Use RESPONSES when...", {
    x: 5.2, y: 1.3, w: 4.0, h: 0.5,
    fontSize: 13, fontFace: FONT.heading, color: COLORS.white, align: "center", valign: "middle", bold: true,
  });

  const responses = [
    "Interactive conversation needed",
    "User asks follow-up questions",
    "Model should decide which tools to use",
    "Real-time research (web search)",
    "Exploratory analysis (code interpreter)",
    "Behavioral guidelines change often (Skills)",
  ];

  slide.addText(
    responses.map(r => ({ text: r, options: { bullet: true, breakLine: true } })),
    { x: 5.3, y: 1.9, w: 3.8, h: 3.0, fontSize: 12, fontFace: FONT.body, color: COLORS.dark, lineSpacingMultiple: 1.5 }
  );

  // Bottom callout
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.8, y: 5.0, w: 8.4, h: 0.5,
    fill: { color: COLORS.light },
  });
  slide.addText(
    "The sample uses BOTH: Invocations for automated Benefits Review + Responses for interactive advisory",
    {
      x: 1.0, y: 5.0, w: 8.0, h: 0.5,
      fontSize: 12, fontFace: FONT.heading, color: COLORS.primary, bold: true, align: "center", valign: "middle",
    }
  );
}

function addClosingSlide(pres) {
  let slide = pres.addSlide();
  slide.background = { color: COLORS.dark };

  slide.addText("Summary", {
    x: 0.8, y: 0.8, w: 8.4, h: 0.7,
    fontSize: 32, fontFace: FONT.heading, color: COLORS.white, bold: true,
  });

  const points = [
    "Two protocols serve different use cases — not competing, complementary",
    "Invocations: structured, deterministic, batch (Benefits Review = 160 rows)",
    "Responses: conversational, model-directed, interactive (Benefits Advisor)",
    "Foundry Toolbox: web_search + code_interpreter via MCP (model decides when)",
    "Foundry Skills: domain knowledge decoupled from code (update without redeploy)",
    "Both protocols run on the same Foundry hosting infrastructure",
  ];

  slide.addText(
    points.map(p => ({ text: p, options: { bullet: true, breakLine: true } })),
    { x: 1.0, y: 1.8, w: 8.0, h: 3.2, fontSize: 14, fontFace: FONT.body, color: COLORS.white, lineSpacingMultiple: 1.6 }
  );

  slide.addText("Questions?", {
    x: 0.8, y: 5.0, w: 8.4, h: 0.4,
    fontSize: 18, fontFace: FONT.heading, color: COLORS.secondary, bold: true,
  });
}

// --- Generate ---

async function generate() {
  let pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.author = "Kapil Dhanger";
  pres.title = "Hosted Agents: Invocations vs Responses Protocol";

  addTitleSlide(pres);
  addAgendaSlide(pres);
  addWhatAreHostedAgents(pres);
  addInvocationsProtocol(pres);
  addResponsesProtocol(pres);
  addKeyDifferences(pres);
  addToolboxSlide(pres);
  addSkillsSlide(pres);
  addArchitectureSlide(pres);
  addDemoWalkthrough(pres);
  addRunInstructions(pres);
  addWhenToUseWhich(pres);
  addClosingSlide(pres);

  const path = require("path");
  const outputPath = path.join(__dirname, "..", "..", "docs", "Hosted_Agents_Protocol_Comparison.pptx");
  // Ensure docs directory exists
  const fs = require("fs");
  const docsDir = path.dirname(outputPath);
  if (!fs.existsSync(docsDir)) { fs.mkdirSync(docsDir, { recursive: true }); }
  await pres.writeFile({ fileName: outputPath });
  console.log(`✅ Deck generated: ${outputPath} (${pres.slides.length} slides)`);
}

generate().catch(err => {
  console.error("❌ Failed:", err);
  process.exit(1);
});
