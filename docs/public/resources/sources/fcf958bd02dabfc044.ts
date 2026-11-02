/**
 * Hello Tool - Minimal custom tool example
 */

import { Type } from "@mariozechner/pi-ai";
import { defineTool, type ExtensionAPI } from "@mariozechner/pi-coding-agent";

// ⭐️ 已讲（10 讲义，A.5 / B.4）：午饭扩展示例沿用这套写法：定义参数 Schema、content 与 execute。
const helloTool = defineTool({
	name: "hello",
	label: "Hello",
	description: "A simple greeting tool",
	parameters: Type.Object({
		name: Type.String({ description: "Name to greet" }),
	}),

	async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
		return {
			content: [{ type: "text", text: `Hello, ${params.name}!` }],
			details: { greeted: params.name },
		};
	},
});

// ⭐️ 已讲（10 讲义，A.5 / B.4）：加载器调用默认导出工厂，工厂登记工具；hello.execute 此时尚未执行。
export default function (pi: ExtensionAPI) {
	pi.registerTool(helloTool);
}
