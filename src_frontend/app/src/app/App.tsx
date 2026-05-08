import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const queryClient = new QueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div>RCA Agent — Alert to Action</div>
    </QueryClientProvider>
  );
}
