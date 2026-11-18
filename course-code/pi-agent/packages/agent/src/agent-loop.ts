/**
 Agent loop that works with AgentMessage throughout.
 Transforms to Message[] only at the LLM call boundary.
 */

import {
	type AssistantMessage,
	type Context,
	EventStream,
	streamSimple,
	type ToolResultMessage,
	validateToolArguments,
} from "@mariozechner/pi-ai";
import type {
	AgentContext,
	AgentEvent,
	AgentLoopConfig,
	AgentMessage,
	AgentTool,
	AgentToolCall,
	AgentToolResult,
	StreamFn,
} from "./types.js";

export type AgentEventSink = (event: AgentEvent) => Promise<void> | void;

/**
 Start an agent loop with a new prompt message.
 The prompt is added to the context and events are emitted for it.
 */
export function agentLoop(
	prompts: AgentMessage[],
	context: AgentContext,
	config: AgentLoopConfig,
	signal?: AbortSignal,
	streamFn?: StreamFn,
): EventStream<AgentEvent, AgentMessage[]> {
	const stream = createAgentStream();

	void runAgentLoop(
		prompts,
		context,
		config,
		async (event) => {
			stream.push(event);
		},
		signal,
		streamFn,
	).then((messages) => {
		stream.end(messages);
	});

	return stream;
}

/**
 Continue an agent loop from the current context without adding a new message.
 Used for retries - context already has user message or tool results.

 Important: The last message in context must convert to a `user` or `toolResult` message
 via `convertToLlm`. If it doesn't, the LLM provider will reject the request.
 This cannot be validated here since `convertToLlm` is only called once per turn.
 */
export function agentLoopContinue(
	context: AgentContext,
	config: AgentLoopConfig,
	signal?: AbortSignal,
	streamFn?: StreamFn,
): EventStream<AgentEvent, AgentMessage[]> {
	if (context.messages.length === 0) {
		throw new Error("Cannot continue: no messages in context");
	}

	if (context.messages[context.messages.length - 1].role === "assistant") {
		throw new Error("Cannot continue from message role: assistant");
	}

	const stream = createAgentStream();

	void runAgentLoopContinue(
		context,
		config,
		async (event) => {
			stream.push(event);
		},
		signal,
		streamFn,
	).then((messages) => {
		stream.end(messages);
	});

	return stream;
}

// ⭐️ 已讲（10 讲义，C.4～C.7）：将本次 [U] 接上旧消息，再交给 runLoop 组织模型与工具交互。
export async function runAgentLoop(
	prompts: AgentMessage[],
	context: AgentContext,
	config: AgentLoopConfig,
	emit: AgentEventSink,
	signal?: AbortSignal,
	streamFn?: StreamFn,
): Promise<AgentMessage[]> {
	const newMessages: AgentMessage[] = [...prompts];
	/*
	 currentContext 是本次循环使用的上下文对象；Agent 实例保存的历史在 this._state.messages，
	 外部通过 agent.state.messages 访问，没有 state.contextmessage 这个字段。

	 这里两处带 context 的展开，分别操作对象和数组：
	   ...context          在 {} 中展开对象属性，复制 systemPrompt、messages、tools 等字段。
	   ...context.messages 在 [] 中展开数组元素，取出旧消息，再接上 ...prompts 中的新消息。
	 例如 H1、H2、U 是消息对象的简称，T 是一个工具对象的简称：
	   ⭐️context = { systemPrompt: "请用中文回答", messages: [H1, H2], tools: [T] };
	   ⭐️prompts = [U];
	 第一步，...context 相当于先复制这些字段：
	   ⭐️{ systemPrompt: context.systemPrompt, messages: context.messages, tools: context.tools }
	 此时复制过来的 messages 仍指向原数组。第二步，后写的 messages 字段覆盖前面的同名字段：
	   ⭐️messages: [...context.messages, ...prompts]  →  新数组 [H1, H2, U]
	 所以最终 currentContext 相当于：
	   ⭐️{ systemPrompt: "请用中文回答", messages: [H1, H2, U], tools: [T] }
	 ⭐️也就是保留系统提示词和工具等属性，同时把消息列表换成“旧历史 + 本次输入”的新数组。
	 ⭐️此时 currentContext.messages !== context.messages，但 currentContext.tools === context.tools；
	 消息数组中的 H1、H2 也仍是原来的对象。这里只复制外层，没有深复制消息或工具。
	 顺序也有意义：如果把 ...context 写在新的 messages 字段后面，旧 messages 就会覆盖合并结果。

	 在 Agent.prompt 路径中，createContextSnapshot() 先用 slice() 复制状态消息数组，
	 这里再将旧历史 context.messages 与本次 prompts 合成一个新的 messages 数组。
	 例如旧历史为 [H1, H2]，本次输入为 [U]，这里得到 [H1, H2, U]；外层数组与状态数组不同，
	 其中已有的消息对象仍共享引用，属于浅复制。
	 循环在 currentContext.messages 中追加助手消息、工具结果，流式期间也会暂存当前助手消息；
	 Agent 则通过 emit(message_end) → processEvents() 将完成消息另行追加到 this._state.messages。
	 所以两份数组在消息处理完成后可以内容一致，但各自通过不同语句更新，不是同一个数组。
	 */
	const currentContext: AgentContext = {
		...context,
		messages: [...context.messages, ...prompts],
	};

	await emit({ type: "agent_start" });
	await emit({ type: "turn_start" });
	/*
	 prompts 是本次一起提交的输入消息数组，一个元素代表一条完整消息；旧历史在 context.messages 中。
	 例 1：await agent.prompt("解释 Agent Loop") 会被规范化为 [U1]，所以这里只遍历一次。
	 例 2：调用方也可以一次提交两条消息：
	   const U1: AgentMessage = { role: "user", content: "解释 Agent Loop", timestamp: 0 };
	   const U2: AgentMessage = { role: "user", content: "请结合工具调用举例", timestamp: 1 };
	   await agent.prompt([U1, U2]);
	 此时 prompts = [U1, U2]，依次发出：
	   message_start(U1) → message_end(U1) → message_start(U2) → message_end(U2)。
	 输入消息已经完整提供，因此 start 后可以立即 end，不需要等待文字增量；
	 在 Agent 路径中，message_end 还会让 processEvents 把这条输入加入 state.messages。
	 这里遍历两次只是在报告两条输入消息，不是在分别请求两次模型；
	 下面 runLoop 会使用同时包含 U1、U2 的上下文请求模型，之后是否继续请求由循环决定。
	 */
	for (const prompt of prompts) {
		await emit({ type: "message_start", message: prompt });
		await emit({ type: "message_end", message: prompt });
	}

	await runLoop(currentContext, newMessages, config, signal, emit, streamFn);
	return newMessages;
}

export async function runAgentLoopContinue(
	context: AgentContext,
	config: AgentLoopConfig,
	emit: AgentEventSink,
	signal?: AbortSignal,
	streamFn?: StreamFn,
): Promise<AgentMessage[]> {
	if (context.messages.length === 0) {
		throw new Error("Cannot continue: no messages in context");
	}

	if (context.messages[context.messages.length - 1].role === "assistant") {
		throw new Error("Cannot continue from message role: assistant");
	}

	const newMessages: AgentMessage[] = [];
	// Continue 入口只浅复制上下文对象，messages 沿用传入数组；Agent.continue() 传入的仍是状态快照。
	const currentContext: AgentContext = { ...context };

	await emit({ type: "agent_start" });
	await emit({ type: "turn_start" });

	await runLoop(currentContext, newMessages, config, signal, emit, streamFn);
	return newMessages;
}

function createAgentStream(): EventStream<AgentEvent, AgentMessage[]> {
	return new EventStream<AgentEvent, AgentMessage[]>(
		(event: AgentEvent) => event.type === "agent_end",
		(event: AgentEvent) => (event.type === "agent_end" ? event.messages : []),
	);
}

/**
 Main loop logic shared by agentLoop and agentLoopContinue.
 */
// ⭐️ 已讲（10 讲义，C.4～C.7）：反复请求模型、执行其工具请求并接回结果，直到本次运行可以结束。
async function runLoop(
	currentContext: AgentContext,
	newMessages: AgentMessage[],
	config: AgentLoopConfig,
	signal: AbortSignal | undefined,
	emit: AgentEventSink,
	streamFn?: StreamFn,
): Promise<void> {
	let firstTurn = true;
	// Check for steering messages at start (user may have typed while waiting)
	let pendingMessages: AgentMessage[] = (await config.getSteeringMessages?.()) || [];

	// Outer loop: continues when queued follow-up messages arrive after agent would stop
	while (true) {
		let hasMoreToolCalls = true;

		// Inner loop: process tool calls and steering messages
		while (hasMoreToolCalls || pendingMessages.length > 0) {
			if (!firstTurn) {
				await emit({ type: "turn_start" });
			} else {
				firstTurn = false;
			}

			// Process pending messages (inject before next assistant response)
			if (pendingMessages.length > 0) {
				for (const message of pendingMessages) {
					await emit({ type: "message_start", message });
					await emit({ type: "message_end", message });
					currentContext.messages.push(message);
					newMessages.push(message);
				}
				pendingMessages = [];
			}

			// Stream assistant response
			const message = await streamAssistantResponse(currentContext, config, signal, emit, streamFn);
			newMessages.push(message);

			if (message.stopReason === "error" || message.stopReason === "aborted") {
				await emit({ type: "turn_end", message, toolResults: [] });
				await emit({ type: "agent_end", messages: newMessages });
				return;
			}

			// Check for tool calls
			const toolCalls = message.content.filter((c) => c.type === "toolCall");

			const toolResults: ToolResultMessage[] = [];
			hasMoreToolCalls = false;
			if (toolCalls.length > 0) {
				const executedToolBatch = await executeToolCalls(currentContext, message, config, signal, emit);
				toolResults.push(...executedToolBatch.messages);
				hasMoreToolCalls = !executedToolBatch.terminate;

				// ⭐️ 已讲（10 讲义，C.4～C.7）：把 R1 等工具结果追加进当前消息；正文由下一次模型请求消费。
				for (const result of toolResults) {
					currentContext.messages.push(result);
					newMessages.push(result);
				}
			}

			await emit({ type: "turn_end", message, toolResults });

			pendingMessages = (await config.getSteeringMessages?.()) || [];
		}

		// Agent would stop here. Check for follow-up messages.
		const followUpMessages = (await config.getFollowUpMessages?.()) || [];
		if (followUpMessages.length > 0) {
			// Set as pending so inner loop processes them
			pendingMessages = followUpMessages;
			continue;
		}

		// No more messages, exit
		break;
	}

	await emit({ type: "agent_end", messages: newMessages });
}

/**
 Stream an assistant response from the LLM.
 This is where AgentMessage[] gets transformed to Message[] for the LLM.
 */
// ⭐️ 已讲（10 讲义，C.4～C.7）：把消息变换为 LLM 格式，与独立的 systemPrompt/tools 一起交给模型函数。
async function streamAssistantResponse(
	context: AgentContext,
	config: AgentLoopConfig,
	signal: AbortSignal | undefined,
	emit: AgentEventSink,
	streamFn?: StreamFn,
): Promise<AssistantMessage> {
	/*
	 context.messages 是按对话顺序排列的消息对象数组，类型为 AgentMessage[]，不是一段拼接好的字符串。
	 示例（省略 timestamp、模型信息、usage 等字段）：
	 [
	   { role: "user", content: "读取 README.md" },
	   { role: "assistant", content: [
	     { type: "text", text: "我来读取文件。" },
	     { type: "toolCall", id: "call_1", name: "read", arguments: { path: "README.md" } }
	   ] },
	   { role: "toolResult", toolCallId: "call_1", toolName: "read",
	     content: [{ type: "text", text: "文件内容……" }], isError: false },
	   { role: "assistant", content: [{ type: "text", text: "README 的主要内容是……" }] }
	 ]
	 role 表示消息来源；content 是消息内容，助手消息的 content 数组可混合文本、思考和工具调用。
	 工具结果通过 toolCallId 对应助手发出的工具调用；应用还可以扩展自定义消息类型。
	 系统提示词单独保存在 context.systemPrompt 中；此数组只包含当前上下文保留的消息。
	 流式生成时，下方代码先 push 当前助手消息，再不断替换最后一条，使其内容随生成进度更新。
	 */
	// Apply context transform if configured (AgentMessage[] → AgentMessage[])
	let messages = context.messages;
	if (config.transformContext) {
		messages = await config.transformContext(messages, signal);
	}

	// Convert to LLM-compatible messages (AgentMessage[] → Message[])
	const llmMessages = await config.convertToLlm(messages);

	// Build LLM context
	// ⭐️ 已讲（10 讲义，C.4～C.7）：本例首次 messages=[U]；读取 Skill 后下一次变为 [U,A1,R1]。
	const llmContext: Context = {
		systemPrompt: context.systemPrompt,
		messages: llmMessages,
		tools: context.tools,
	};

	const streamFunction = streamFn || streamSimple;

	// Resolve API key (important for expiring tokens)
	const resolvedApiKey =
		(config.getApiKey ? await config.getApiKey(config.model.provider) : undefined) || config.apiKey;

	const response = await streamFunction(config.model, llmContext, {
		...config,
		apiKey: resolvedApiKey,
		signal,
	});

	// partial 指尚未生成完成的消息：保存本次助手回复到当前为止累积的内容（文本、思考、工具调用等）。
	// 它不是整个对话的全部消息，也不是本次新增的一小段 delta；例如依次收到“你”“好”，累积内容就是“你好”。
	// 类型允许为 AssistantMessage 或 null；初始为 null，表示尚未收到消息开始事件。
	let partialMessage: AssistantMessage | null = null;
	// 标记这条生成中的助手消息是否已加入 context.messages（整个对话的消息列表）。
	// start 事件中加入后设为 true；后续更新和结束时替换最后一条，结束时若仍为 false 则追加最终消息，避免重复加入。
	let addedPartial = false;

	for await (const event of response) {
		switch (event.type) {
			case "start":
				partialMessage = event.partial;
				context.messages.push(partialMessage);
				addedPartial = true;
				await emit({ type: "message_start", message: { ...partialMessage } });
				break;

			case "text_start":
			case "text_delta":
			case "text_end":
			case "thinking_start":
			case "thinking_delta":
			case "thinking_end":
			case "toolcall_start":
			case "toolcall_delta":
			case "toolcall_end":
				if (partialMessage) {
					partialMessage = event.partial;
					context.messages[context.messages.length - 1] = partialMessage;
					await emit({
						type: "message_update",
						assistantMessageEvent: event,
						message: { ...partialMessage },
					});
				}
				break;

			case "done":
			case "error": {
				const finalMessage = await response.result();
				if (addedPartial) {
					context.messages[context.messages.length - 1] = finalMessage;
				} else {
					context.messages.push(finalMessage);
				}
				if (!addedPartial) {
					await emit({ type: "message_start", message: { ...finalMessage } });
				}
				await emit({ type: "message_end", message: finalMessage });
				return finalMessage;
			}
		}
	}

	const finalMessage = await response.result();
	if (addedPartial) {
		/*
		 例：此前收到 start，已加入当前助手消息，列表为 [用户("你好"), 助手生成中("你…")]。
		 用最终结果替换最后一条后，变为 [用户("你好"), 助手最终消息("你好！")]。
		 当前回复已经占了一个位置；若再 push，会把同一次回复保存成两条消息。
		 替换整个对象，也能保存最终的 usage、stopReason 等字段；此前已发过 message_start，无需重复发。
		 */
		context.messages[context.messages.length - 1] = finalMessage;
	} else {
		/*
		 例：未收到 start，当前助手消息尚未加入，列表仍为 [用户("你好")]。
		 追加最终结果后，变为 [用户("你好"), 助手最终消息("你好！")]。
		 此时最后一条仍是历史消息，直接替换会覆盖它，所以必须 push。
		 此前也未发过 message_start，需要补发，再由下方发出 message_end，让界面收到完整的消息生命周期。
		 这是事件流未按常规发出 start 时的兜底处理；正常事件流应先发 start。
		 */
		context.messages.push(finalMessage);
		await emit({ type: "message_start", message: { ...finalMessage } });
	}
	await emit({ type: "message_end", message: finalMessage });
	return finalMessage;
}

/**
 Execute tool calls from an assistant message.
 */
// ⭐️ 已讲（10 讲义，C.4～C.7）：从助手消息提取 toolCall，再选择顺序或并行执行；不是执行 Skill Markdown。
async function executeToolCalls(
	currentContext: AgentContext,
	assistantMessage: AssistantMessage,
	config: AgentLoopConfig,
	signal: AbortSignal | undefined,
	emit: AgentEventSink,
): Promise<ExecutedToolCallBatch> {
	const toolCalls = assistantMessage.content.filter((c) => c.type === "toolCall");
	const hasSequentialToolCall = toolCalls.some(
		(tc) => currentContext.tools?.find((t) => t.name === tc.name)?.executionMode === "sequential",
	);
	if (config.toolExecution === "sequential" || hasSequentialToolCall) {
		return executeToolCallsSequential(currentContext, assistantMessage, toolCalls, config, signal, emit);
	}
	return executeToolCallsParallel(currentContext, assistantMessage, toolCalls, config, signal, emit);
}

type ExecutedToolCallBatch = {
	messages: ToolResultMessage[];
	terminate: boolean;
};

// ⭐️ 已讲（10 讲义，C.4～C.7）：依次准备、执行并包装工具结果；即时错误分支跳过 execute。
async function executeToolCallsSequential(
	currentContext: AgentContext,
	assistantMessage: AssistantMessage,
	toolCalls: AgentToolCall[],
	config: AgentLoopConfig,
	signal: AbortSignal | undefined,
	emit: AgentEventSink,
): Promise<ExecutedToolCallBatch> {
	const finalizedCalls: FinalizedToolCallOutcome[] = [];
	const messages: ToolResultMessage[] = [];

	for (const toolCall of toolCalls) {
		await emit({
			type: "tool_execution_start",
			toolCallId: toolCall.id,
			toolName: toolCall.name,
			args: toolCall.arguments,
		});

		const preparation = await prepareToolCall(currentContext, assistantMessage, toolCall, config, signal);
		let finalized: FinalizedToolCallOutcome;
		if (preparation.kind === "immediate") {
			finalized = {
				toolCall,
				result: preparation.result,
				isError: preparation.isError,
			};
		} else {
			const executed = await executePreparedToolCall(preparation, signal, emit);
			finalized = await finalizeExecutedToolCall(
				currentContext,
				assistantMessage,
				preparation,
				executed,
				config,
				signal,
			);
		}

		await emitToolExecutionEnd(finalized, emit);
		const toolResultMessage = createToolResultMessage(finalized);
		await emitToolResultMessage(toolResultMessage, emit);
		finalizedCalls.push(finalized);
		messages.push(toolResultMessage);
	}

	return {
		messages,
		terminate: shouldTerminateToolBatch(finalizedCalls),
	};
}

// ⭐️ 已讲（10 讲义，C.4～C.7）：先准备各调用，再执行可运行项并按原调用顺序交回结果。
async function executeToolCallsParallel(
	currentContext: AgentContext,
	assistantMessage: AssistantMessage,
	toolCalls: AgentToolCall[],
	config: AgentLoopConfig,
	signal: AbortSignal | undefined,
	emit: AgentEventSink,
): Promise<ExecutedToolCallBatch> {
	const finalizedCalls: FinalizedToolCallEntry[] = [];

	for (const toolCall of toolCalls) {
		await emit({
			type: "tool_execution_start",
			toolCallId: toolCall.id,
			toolName: toolCall.name,
			args: toolCall.arguments,
		});

		const preparation = await prepareToolCall(currentContext, assistantMessage, toolCall, config, signal);
		if (preparation.kind === "immediate") { //有错误立即返回
			const finalized = {
				toolCall,
				result: preparation.result,
				isError: preparation.isError,
			} satisfies FinalizedToolCallOutcome;
			await emitToolExecutionEnd(finalized, emit);
			finalizedCalls.push(finalized);
			continue;
		}

		finalizedCalls.push(async () => {
			const executed = await executePreparedToolCall(preparation, signal, emit);
			const finalized = await finalizeExecutedToolCall(
				currentContext,
				assistantMessage,
				preparation,
				executed,
				config,
				signal,
			);
			await emitToolExecutionEnd(finalized, emit);
			return finalized;
		});
	}

	const orderedFinalizedCalls = await Promise.all(
		finalizedCalls.map((entry) => (typeof entry === "function" ? entry() : Promise.resolve(entry))),
	);
	const messages: ToolResultMessage[] = [];
	for (const finalized of orderedFinalizedCalls) {
		const toolResultMessage = createToolResultMessage(finalized);
		await emitToolResultMessage(toolResultMessage, emit);
		messages.push(toolResultMessage);
	}

	return {
		messages,
		terminate: shouldTerminateToolBatch(orderedFinalizedCalls),
	};
}

type PreparedToolCall = {
	kind: "prepared";
	toolCall: AgentToolCall;
	tool: AgentTool<any>;
	args: unknown;
};

type ImmediateToolCallOutcome = {
	kind: "immediate";
	result: AgentToolResult<any>;
	isError: boolean;
};

type ExecutedToolCallOutcome = {
	result: AgentToolResult<any>;
	isError: boolean;
};

type FinalizedToolCallOutcome = {
	toolCall: AgentToolCall;
	result: AgentToolResult<any>;
	isError: boolean;
};

type FinalizedToolCallEntry = FinalizedToolCallOutcome | (() => Promise<FinalizedToolCallOutcome>);

function shouldTerminateToolBatch(finalizedCalls: FinalizedToolCallOutcome[]): boolean {
	return finalizedCalls.length > 0 && finalizedCalls.every((finalized) => finalized.result.terminate === true);
}

function prepareToolCallArguments(tool: AgentTool<any>, toolCall: AgentToolCall): AgentToolCall {
	if (!tool.prepareArguments) {
		return toolCall;
	}
	const preparedArguments = tool.prepareArguments(toolCall.arguments);
	if (preparedArguments === toolCall.arguments) {
		return toolCall;
	}
	return {
		...toolCall,
		arguments: preparedArguments as Record<string, any>,
	};
}

// ⭐️ 已讲（10 讲义，C.4～C.7）：按工具名查活跃对象、准备并校验参数，随后询问 beforeToolCall。
async function prepareToolCall(
	currentContext: AgentContext,
	assistantMessage: AssistantMessage,
	toolCall: AgentToolCall,
	config: AgentLoopConfig,
	signal: AbortSignal | undefined,
): Promise<PreparedToolCall | ImmediateToolCallOutcome> {
	const tool = currentContext.tools?.find((t) => t.name === toolCall.name);
	if (!tool) {
		return {
			kind: "immediate",
			result: createErrorToolResult(`Tool ${toolCall.name} not found`),
			isError: true,
		};
	}

	try {
		const preparedToolCall = prepareToolCallArguments(tool, toolCall);
		const validatedArgs = validateToolArguments(tool, preparedToolCall);
		if (config.beforeToolCall) {
			const beforeResult = await config.beforeToolCall(
				{
					assistantMessage,
					toolCall,
					args: validatedArgs,
					context: currentContext,
				},
				signal,
			);
			// ⭐️ 已讲（10 讲义，C.4～C.7）：拦截器返回 block 后生成即时错误，避免调用 place_order.execute。
			if (beforeResult?.block) {
				return {
					kind: "immediate",
					result: createErrorToolResult(beforeResult.reason || "Tool execution was blocked"),
					isError: true,
				};
			}
		}
		return {
			kind: "prepared",
			toolCall,
			tool,
			args: validatedArgs,
		};
	} catch (error) {
		return {
			kind: "immediate",
			result: createErrorToolResult(error instanceof Error ? error.message : String(error)),
			isError: true,
		};
	}
}

// ⭐️ 已讲（10 讲义，C.4～C.7）：把 toolCall.id、已校验参数和进度回调传给真实工具 execute。
async function executePreparedToolCall(
	prepared: PreparedToolCall,
	signal: AbortSignal | undefined,
	emit: AgentEventSink,
): Promise<ExecutedToolCallOutcome> {
	const updateEvents: Promise<void>[] = [];

	try {
		const result = await prepared.tool.execute(
			prepared.toolCall.id,
			prepared.args as never,
			signal,
			(partialResult) => { //回调函数
				updateEvents.push(
					Promise.resolve(
						emit({
							type: "tool_execution_update",
							toolCallId: prepared.toolCall.id,
							toolName: prepared.toolCall.name,
							args: prepared.toolCall.arguments,
							partialResult,
						}),
					),
				);
			},
		);
		await Promise.all(updateEvents);
		return { result, isError: false };
	} catch (error) {
		await Promise.all(updateEvents);
		return {
			result: createErrorToolResult(error instanceof Error ? error.message : String(error)),
			isError: true,
		};
	}
}

// ⭐️ 已讲（10 讲义，C.4～C.7）：接回 execute 的结果并应用执行后钩子，再交给消息包装。
async function finalizeExecutedToolCall(
	currentContext: AgentContext,
	assistantMessage: AssistantMessage,
	prepared: PreparedToolCall,
	executed: ExecutedToolCallOutcome,
	config: AgentLoopConfig,
	signal: AbortSignal | undefined,
): Promise<FinalizedToolCallOutcome> {
	let result = executed.result;
	let isError = executed.isError;

	if (config.afterToolCall) {
		try {
			const afterResult = await config.afterToolCall(
				{
					assistantMessage,
					toolCall: prepared.toolCall,
					args: prepared.args,
					result,
					isError,
					context: currentContext,
				},
				signal,
			);
			if (afterResult) {
				result = {
					content: afterResult.content ?? result.content,
					details: afterResult.details ?? result.details,
					terminate: afterResult.terminate ?? result.terminate,
				};
				isError = afterResult.isError ?? isError;
			}
		} catch (error) {
			result = createErrorToolResult(error instanceof Error ? error.message : String(error));
			isError = true;
		}
	}

	return {
		toolCall: prepared.toolCall,
		result,
		isError,
	};
}

function createErrorToolResult(message: string): AgentToolResult<any> {
	return {
		content: [{ type: "text", text: message }],
		details: {},
	};
}

async function emitToolExecutionEnd(finalized: FinalizedToolCallOutcome, emit: AgentEventSink): Promise<void> {
	await emit({
		type: "tool_execution_end",
		toolCallId: finalized.toolCall.id,
		toolName: finalized.toolCall.name,
		result: finalized.result,
		isError: finalized.isError,
	});
}

// ⭐️ 已讲（10 讲义，C.4～C.7）：生成 role=toolResult 的 R 消息，用 toolCallId 对应原来的 A 中的工具调用。
function createToolResultMessage(finalized: FinalizedToolCallOutcome): ToolResultMessage {
	return {
		role: "toolResult",
		toolCallId: finalized.toolCall.id,
		toolName: finalized.toolCall.name,
		content: finalized.result.content,
		details: finalized.result.details,
		isError: finalized.isError,
		timestamp: Date.now(),
	};
}

async function emitToolResultMessage(toolResultMessage: ToolResultMessage, emit: AgentEventSink): Promise<void> {
	await emit({ type: "message_start", message: toolResultMessage });
	await emit({ type: "message_end", message: toolResultMessage });
}
