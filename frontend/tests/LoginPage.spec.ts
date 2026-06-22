import { defineComponent } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "../src/pages/LoginPage.vue";

const login = vi.hoisted(() => vi.fn());
const localStorage = createStorage();

Object.defineProperty(window, "localStorage", { configurable: true, value: localStorage });

vi.mock("../src/api/client", () => ({ login }));

function createStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() { return values.size; },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => values.delete(key),
    setItem: (key, value) => values.set(key, value),
  };
}

const FormStub = defineComponent({
  template: "<div><slot /></div>",
});

const InputStub = defineComponent({
  props: { modelValue: { type: String, default: "" } },
  emits: ["update:modelValue"],
  template: `<input :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />`,
});

describe("LoginPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
    login.mockReset();
  });

  it("stores the token and navigates home after login", async () => {
    login.mockResolvedValue({
      access_token: "header.eyJzdWIiOiJkZW1vX3VzZXIifQ.signature",
      token_type: "bearer",
      username: "demo_user",
    });
    const testRouter = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/", component: { template: "<div />" } },
        { path: "/login", component: LoginPage },
      ],
    });
    await testRouter.push("/login");
    await testRouter.isReady();
    const wrapper = mount(LoginPage, {
      global: {
        plugins: [testRouter],
        stubs: {
          "el-form": FormStub,
          "el-form-item": FormStub,
          "el-icon": true,
          "el-input": InputStub,
        },
      },
    });

    const inputs = wrapper.findAll("input");
    await inputs[0].setValue("demo_user");
    await inputs[1].setValue("demo12345");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(login).toHaveBeenCalledWith("demo_user", "demo12345");
    expect(window.localStorage.getItem("auth_token")).toContain("eyJzdWIiOiJkZW1vX3VzZXIifQ");
    expect(testRouter.currentRoute.value.path).toBe("/");
  });
});
