#pragma once
#include "Framework.h"

#include <thread_pool.h>

namespace RLGC {
	// Modified version of https://stackoverflow.com/questions/26516683/reusing-thread-in-loop-c
	struct ThreadPool {

		dp::thread_pool<>* _tp;

		ThreadPool() {
			auto text = std::getenv("GIGAFORGE_SIM_THREADS");
            int count = text ? std::stoi(text) : int(std::min(8u,std::max(1u,std::thread::hardware_concurrency()/2)));
            if(count<1 || count>64) throw std::runtime_error("Invalid simulation thread count");
            _tp = new dp::thread_pool(count);
		}

		RG_NO_COPY(ThreadPool);

		~ThreadPool() {
			delete _tp;
		}

		template <typename Function, typename... Args> requires std::invocable<Function, Args...>
		void StartJobAsync(Function&& func, Args &&...args) {
			_tp->enqueue_detach(func, args...);
		}

		void StartBatchedJobs(std::function<void(int)> func, int num, bool async) {

			for (int i = 0; i < num; i++)
				StartJobAsync(func, i);

			if (!async)
				WaitUntilDone();
		}

		void WaitUntilDone() {
			_tp->wait_for_tasks();
		}

		int GetNumThreads() const {
			return _tp->size();
		}
	};

	extern ThreadPool g_ThreadPool;
}