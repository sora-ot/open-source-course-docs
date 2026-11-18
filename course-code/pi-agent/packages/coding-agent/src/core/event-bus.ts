import { EventEmitter } from "node:events";

// ⭐️ 已讲（12 讲义，第 6.2 节）：定义扩展间共享频道的发布与订阅接口。
export interface EventBus {
	emit(channel: string, data: unknown): void;
	on(channel: string, handler: (data: unknown) => void): () => void;
}

// ⭐️ 已讲（12 讲义，第 6.2 节）：为总线增加清空订阅的管理能力。
export interface EventBusController extends EventBus {
	clear(): void;
}

// ⭐️ 已讲（12 讲义，第 6.2 节）：基于 EventEmitter 建立共享总线，on 返回取消订阅函数。
export function createEventBus(): EventBusController {
	const emitter = new EventEmitter();
	return {
		emit: (channel, data) => {
			emitter.emit(channel, data);
		},
		on: (channel, handler) => {
			const safeHandler = async (data: unknown) => {
				try {
					await handler(data);
				} catch (err) {
					console.error(`Event handler error (${channel}):`, err);
				}
			};
			emitter.on(channel, safeHandler);
			return () => emitter.off(channel, safeHandler);
		},
		clear: () => {
			emitter.removeAllListeners();
		},
	};
}
