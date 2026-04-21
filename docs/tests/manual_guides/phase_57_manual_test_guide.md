# Phase 57 Manual Test Guide: Context Intelligence

This guide describes how to manually verify the Context Intelligence Upgrade implemented in Phase 57, ensuring that the Waterfall Budget and Visual Silent Downgrade mechanisms work effectively in a real-world scenario.

## Test 1: Waterfall Budget & Injection

**Objective**: Verify that context elements (KG, Experience, Action History, Reminder, RAG) are injected according to their strict priority limits and do not collectively exceed the 8000 character maximum limit (`_CONTEXT_BUDGET`).

**Steps**:
1. Open the Nanobot dashboard.
2. Select the `gpt-4o` or `claude-3-5-sonnet-20241022` model.
3. Trigger a scenario that involves a dense knowledge graph lookup, an experience rule, and heavy RAG context.
   - Example prompt: `Explain the detailed internal logic of our memory architecture, specifically focusing on ContextBuilder, IFCC, and the Waterfall Budget mechanisms.`
4. Monitor the debug system logs (`logger.debug`). You should see output indicating RAG context was added and truncated.
5. In the generated artifact, ask the bot to output the estimated length of its system prompt or check the backend debug logs. Verify the injected layer `build_messages` does not exceed 8000.

**Expected Outcome**: 
- Action History, KG, Experience, and Reminder text should all be present in the initial prompt securely within bounded `_ACTION_HIST_CAP` limits without RAG monopolizing the tokens.

## Test 2: Visual Silent Downgrade

**Objective**: Verify that after a session spans more than `_VISUAL_HOT_STEPS` (3), older visually intact multimodel messages are downgraded quietly to pure text block annotations, saving immense token budgets.

**Steps**:
1. Upload an image (e.g., a chart) to the chat, ask: `What's in this chart?`
2. Next, upload a second image: `And this one?`
3. Upload a third: `And this one?`
4. Upload a fourth independent image without asking about previous images.
5. On the 5th message (e.g., `Summarize what we discussed`), the framework's memory window will pass through `_trim_history()`.
6. Inspect the API request payloads sent to OpenAI/Anthropic using your proxy debugger. 

**Expected Outcome**:
- The prompt history sent to the LLM should contain the latest 3 images fully encoded in base64 blocks standard to vision capability.
- The 1st and 2nd images should have been replaced entirely by a text placeholder `[视觉快照已折叠，保留锚点信息]` along with whatever diagnostic text accompanied it.
- This will drop thousands of tokens silently without triggering a separate API summarization call.
