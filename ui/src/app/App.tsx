import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { createQueryClient } from "./queryClient";
import { AppRouter } from "./router";
import { ActiveOperationsBootstrap } from "../features/operations/ActiveOperationsBootstrap";

const queryClient = createQueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ActiveOperationsBootstrap />
        <AppRouter />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
