import { type ReactNode, useState } from 'react';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { zodResolver } from '@hookform/resolvers/zod';
import { type UseFormReturn } from 'react-hook-form';
import { z } from 'zod';
import {
  getGetCurrentAccountQueryKey,
  getHealthCheckQueryKey,
  getReadinessCheckQueryKey,
  useGetCurrentAccount,
  useHealthCheck,
  useLoginAccount,
  useLogoutAccount,
  useReadinessCheck,
  useRegisterAccount,
  useListUniverses,
  useCreateUniverse,
  type Account,
  type UniverseResponse,
} from '@workspace/api-client-react';
import UniverseDetail from '@/pages/UniverseDetail';
import { ArrowDownRight, ArrowRight, BookOpen, Check, KeyRound, LogOut, Plus, ShieldCheck } from 'lucide-react';
import { Link, Route, Switch, useLocation, Router as WouterRouter } from 'wouter';
import { ErrorBoundary } from '@/components/error-boundary';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage, useForm } from '@/components/ui/form';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import NotFound from '@/pages/not-found';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

function describeError(error: unknown, fallback: string) {
  if (!error || typeof error !== 'object') return fallback;
  const value = error as {
    message?: string;
    error?: { message?: string };
    data?: { error?: { message?: string } };
  };
  return value.data?.error?.message || value.error?.message || value.message || fallback;
}

function Wordmark() {
  return (
    <Link href="/" className="ww-wordmark flex items-center gap-3 text-[25px] text-[#253a32] no-underline" data-testid="link-worldweave-home">
      <span className="flex h-9 w-9 items-center justify-center rounded-full border border-[#aa573f]/45 text-[#9b4a36]">
        <BookOpen size={17} strokeWidth={1.5} />
      </span>
      <span>worldweave<span className="text-[#a4523b]">.</span></span>
    </Link>
  );
}

function HealthRibbon() {
  const health = useHealthCheck({ query: { queryKey: getHealthCheckQueryKey(), staleTime: 60_000 } });
  const readiness = useReadinessCheck({ query: { queryKey: getReadinessCheckQueryKey(), staleTime: 60_000 } });
  const ready = health.data?.status === 'healthy' && readiness.data?.status === 'ready';
  const checking = health.isLoading || readiness.isLoading;
  const state = checking ? 'checking' : ready ? 'ready' : 'attention';
  return (
    <div className="flex items-center gap-2.5 text-[11px] text-[#53655b]" data-testid="status-instance">
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${ready ? 'bg-[#64856b]' : checking ? 'bg-[#b18b4d]' : 'bg-[#a4523b]'}`} />
      <span className="ww-kicker !text-[9px] !tracking-[.12em]">{checking ? 'Checking instance' : ready ? 'Instance ready' : 'Instance attention'}</span>
      {!ready && !checking && (
        <button
          className="border-0 bg-transparent p-0 text-[11px] underline underline-offset-2 text-[#9b4a36]"
          data-testid="button-retry-health"
          onClick={() => { void health.refetch(); void readiness.refetch(); }}
          type="button"
        >Retry</button>
      )}
      <span className="sr-only" aria-live="polite">{state}</span>
    </div>
  );
}

function Masthead({ mode = 'auth' }: { mode?: 'auth' | 'home' }) {
  return (
    <header className="ww-masthead">
      <div className="mx-auto flex max-w-[1240px] items-center justify-between px-5 py-5 sm:px-8 lg:px-12">
        <Wordmark />
        <div className="flex items-center gap-5">
          <HealthRibbon />
          <span className="hidden h-5 border-l border-[#d8d0c1] sm:block" />
          {mode === 'home' ? (
            <span className="ww-kicker hidden text-[#6e786f] sm:inline">Your private atlas</span>
          ) : (
            <Link href="/login" className="ww-kicker text-[#53655b] no-underline hover:text-[#9b4a36]" data-testid="link-header-login">Sign in</Link>
          )}
        </div>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="mx-auto flex max-w-[1240px] flex-col gap-2 border-t border-[#d8d0c1] px-5 py-6 text-[11px] text-[#788078] sm:flex-row sm:items-center sm:justify-between sm:px-8 lg:px-12">
      <span className="ww-kicker !text-[9px]">A workspace for worlds not yet written</span>
      <span>Self-hosted by design · Your stories stay yours</span>
    </footer>
  );
}

function Frame({ children, mode }: { children: ReactNode; mode?: 'auth' | 'home' }) {
  return (
    <div className="ww-shell flex flex-col">
      <div className="ww-inner"><Masthead mode={mode} /></div>
      <main className="ww-inner flex-1">{children}</main>
      <div className="ww-inner"><Footer /></div>
    </div>
  );
}

type AuthFormValues = {
  display_name?: string;
  email: string;
  password: string;
};

function createAuthSchema(register: boolean) {
  return z.object({
    display_name: z.string().max(80).optional(),
    email: z.string().trim().email('Enter a valid email address.').max(254),
    password: z.string().min(1, 'Enter your password.').max(128),
  }).superRefine((values, context) => {
    if (register && !values.display_name?.trim()) {
      context.addIssue({ code: 'custom', path: ['display_name'], message: 'Add a display name.' });
    }
    if (register && values.password.length < 12) {
      context.addIssue({ code: 'custom', path: ['password'], message: 'Use at least 12 characters.' });
    }
  });
}

function Field({ form, label, name, id, type = 'text', autoComplete, minLength, maxLength }: {
  form: UseFormReturn<AuthFormValues>;
  label: string;
  name: keyof AuthFormValues;
  id: string;
  type?: string;
  autoComplete: string;
  minLength?: number;
  maxLength?: number;
}) {
  return (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem className="space-y-0">
          <FormLabel className="mb-2 block text-[13px] font-semibold text-[#34473d]">{label}</FormLabel>
          <FormControl>
            <input
              {...field}
              value={field.value ?? ''}
              type={type}
              autoComplete={autoComplete}
              minLength={minLength}
              maxLength={maxLength}
              required
              className="w-full rounded-sm border border-[#d5cebf] bg-[#fbf8f0]/80 px-3.5 py-3 text-[14px] text-[#253a32] placeholder:text-[#9a9c90] transition-colors focus:border-[#9b4a36] focus:outline-none"
              data-testid={`input-${id}`}
            />
          </FormControl>
          <FormMessage className="mt-1 text-[11px] leading-4 text-[#9b4a36]" />
        </FormItem>
      )}
    />
  );
}

function AuthPage({ register = false }: { register?: boolean }) {
  const [, setLocation] = useLocation();
  const queryClient = useQueryClient();
  const registerAccount = useRegisterAccount();
  const loginAccount = useLoginAccount();
  const mutation = register ? registerAccount : loginAccount;
  const form = useForm<AuthFormValues>({
    resolver: zodResolver(createAuthSchema(register)),
    defaultValues: { display_name: '', email: '', password: '' },
  });
  const [formError, setFormError] = useState('');
  const busy = mutation.isPending;

  const submit = async (values: AuthFormValues) => {
    setFormError('');
    try {
      const account = register
        ? await registerAccount.mutateAsync({ data: { display_name: values.display_name?.trim() ?? '', email: values.email.trim(), password: values.password } })
        : await loginAccount.mutateAsync({ data: { email: values.email.trim(), password: values.password } });
      queryClient.setQueryData<Account>(getGetCurrentAccountQueryKey(), account);
      await queryClient.invalidateQueries({ queryKey: getGetCurrentAccountQueryKey() });
      setLocation('/');
    } catch (error) {
      setFormError(describeError(error, register ? 'We could not create your account. Please try again.' : 'Those details could not be verified. Please try again.'));
    }
  };

  return (
    <Frame>
      <section className="mx-auto grid max-w-[1120px] items-center gap-12 px-5 py-12 sm:px-8 sm:py-16 lg:grid-cols-[1.02fr_.98fr] lg:gap-20 lg:px-12 lg:py-20">
        <div className="ww-entrance order-2 lg:order-1">
          <div className="mb-5 flex items-center gap-3">
            <span className="h-px w-10 bg-[#a4523b]" />
            <p className="ww-kicker text-[#9b4a36]">{register ? 'Begin your archive' : 'Return to your archive'}</p>
          </div>
          <h1 className="ww-display max-w-[570px] text-[clamp(3.5rem,7vw,6.6rem)] leading-[.88] text-[#263b32]">
            {register ? <>A world<br /><em className="text-[#a4523b]">takes shape</em><br />here.</> : <>The door<br />is still <em className="text-[#a4523b]">open.</em></>}
          </h1>
          <p className="mt-7 max-w-[440px] text-[15px] leading-7 text-[#657168]">
            {register
              ? 'A quiet, structured home for the places, people, histories, and impossible details your stories depend on.'
              : 'Pick up the threads of your private world-building archive, right where you left them.'}
          </p>
          <div className="mt-12 hidden border-t border-[#d8d0c1] pt-5 md:block">
            <div className="flex items-start gap-4">
              <span className="ww-kicker pt-1 text-[#9b4a36]">M1 / 01</span>
              <p className="ww-display max-w-[340px] text-[24px] leading-[1.12] text-[#52645a]">“Every imagined place deserves a record of its own.”</p>
            </div>
          </div>
          <div className="pointer-events-none absolute right-[7%] top-[42%] hidden h-40 w-40 items-center justify-center rounded-full border border-[#b8aa8d]/35 xl:flex">
            <span className="h-28 w-28 rounded-full border border-dashed border-[#b8aa8d]/40" />
            <span className="absolute h-2 w-2 rounded-full bg-[#a4523b]" />
          </div>
        </div>

        <div className="ww-entrance-delay order-1 lg:order-2">
          <div className="relative mx-auto max-w-[450px] border border-[#d9d1c2] bg-[#faf7ef]/85 p-6 shadow-[0_22px_70px_rgba(63,57,42,.08)] sm:p-9">
            <div className="absolute left-0 top-0 h-1 w-20 bg-[#a4523b]" />
            <div className="mb-8 flex items-start justify-between">
              <div>
                <p className="ww-kicker mb-3 text-[#9b4a36]">{register ? 'Create account' : 'Account access'}</p>
                <h2 className="ww-display text-[36px] leading-none text-[#263b32]">{register ? 'Start your atlas' : 'Welcome back'}</h2>
              </div>
              <div className="mt-1 flex h-10 w-10 items-center justify-center rounded-full border border-[#d9d1c2] text-[#9b4a36]">
                {register ? <BookOpen size={17} strokeWidth={1.5} /> : <KeyRound size={17} strokeWidth={1.5} />}
              </div>
            </div>
            <Form {...form}>
            <form onSubmit={form.handleSubmit(submit)} className="space-y-5" data-testid={register ? 'form-register' : 'form-login'}>
              {register && <Field form={form} label="Display name" name="display_name" id="display-name" autoComplete="name" minLength={1} maxLength={80} />}
              <Field form={form} label="Email address" name="email" id="email" type="email" autoComplete="email" maxLength={254} />
              <Field form={form} label="Password" name="password" id="password" type="password" autoComplete={register ? 'new-password' : 'current-password'} minLength={register ? 12 : 1} maxLength={128} />
              {register && <p className="-mt-2 text-[11px] leading-5 text-[#788078]">Use at least 12 characters. Your account is held on this self-hosted instance.</p>}
              {formError && <div role="alert" className="border-l-2 border-[#a4523b] bg-[#f4e8df] px-3 py-2.5 text-[13px] leading-5 text-[#7d3e30]" data-testid="status-auth-error">{formError}</div>}
              <button
                type="submit"
                disabled={busy}
                className="ww-button mt-2 flex w-full items-center justify-between bg-[#294238] px-4 py-3.5 text-[13px] font-semibold tracking-[.02em] text-[#f7f2e7] hover:bg-[#38574a]"
                data-testid="button-submit-auth"
              >
                <span>{busy ? (register ? 'Creating your account…' : 'Signing in…') : (register ? 'Create account' : 'Sign in')}</span>
                {busy ? <span className="h-4 w-4 animate-pulse rounded-full border border-[#f7f2e7]/60" /> : <ArrowRight size={17} />}
              </button>
            </form>
            </Form>
            <div className="mt-7 border-t border-[#ded7ca] pt-5 text-[13px] text-[#69756c]">
              {register ? (
                <p>Already have an account? <Link href="/login" className="font-semibold text-[#9b4a36] underline decoration-[#c7a495] underline-offset-4" data-testid="link-to-login">Sign in</Link></p>
              ) : (
                <p>New to this archive? <Link href="/register" className="font-semibold text-[#9b4a36] underline decoration-[#c7a495] underline-offset-4" data-testid="link-to-register">Create an account</Link></p>
              )}
            </div>
          </div>
          <p className="mx-auto mt-5 max-w-[450px] text-center text-[11px] leading-5 text-[#82877d]">
            <ShieldCheck className="mr-1 inline-block align-[-3px]" size={13} /> No public profiles. No borrowed worlds. Just your own notes, kept close.
          </p>
        </div>
      </section>
    </Frame>
  );
}

function AccountHome() {
  const queryClient = useQueryClient();
  const [, setLocation] = useLocation();
  const account = useGetCurrentAccount({ query: { queryKey: getGetCurrentAccountQueryKey(), retry: false } });
  const logout = useLogoutAccount();
  const [logoutError, setLogoutError] = useState('');
  const signedIn = Boolean(account.data);

  const { data: universeList, refetch: refetchUniverses } = useListUniverses();
  const createUniverse = useCreateUniverse();

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newUniName, setNewUniName] = useState('');
  const [newUniDesc, setNewUniDesc] = useState('');
  const [createError, setCreateError] = useState('');

  const handleCreateUniverse = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUniName.trim()) return;
    setCreateError('');
    try {
      const created = await createUniverse.mutateAsync({
        data: { name: newUniName.trim(), description: newUniDesc.trim() || undefined },
      });
      await refetchUniverses();
      setShowCreateForm(false);
      setNewUniName('');
      setNewUniDesc('');
      setLocation(`/universes/${created.id}`);
    } catch (err: any) {
      setCreateError(err?.data?.error?.message || err?.message || 'Could not create universe.');
    }
  };

  const signOut = async () => {
    setLogoutError('');
    try {
      await logout.mutateAsync();
      await queryClient.invalidateQueries({ queryKey: getGetCurrentAccountQueryKey() });
      queryClient.removeQueries({ queryKey: getGetCurrentAccountQueryKey() });
      setLocation('/login');
    } catch (error) {
      setLogoutError(describeError(error, 'Sign out did not complete. Please try again.'));
    }
  };

  if (account.isLoading) {
    return (
      <Frame mode="home">
        <section className="mx-auto max-w-[1120px] px-5 py-20 sm:px-8 lg:px-12" aria-label="Loading account">
          <div className="h-3 w-28 animate-pulse bg-[#ddd5c6]" />
          <div className="mt-7 h-16 max-w-xl animate-pulse bg-[#e4ddce]" />
          <div className="mt-5 h-5 max-w-md animate-pulse bg-[#e8e1d4]" />
          <div className="mt-14 h-48 max-w-3xl animate-pulse border border-[#ded7ca] bg-[#faf7ef]/60" />
          <p className="ww-kicker mt-5 text-[#788078]" data-testid="status-account-loading">Opening your archive…</p>
        </section>
      </Frame>
    );
  }

  if (account.isError && !signedIn) {
    const statusCode = Number((account.error as { status?: number })?.status);
    const isUnauthenticated = statusCode === 401 || statusCode === 403;
    if (!isUnauthenticated) {
      return (
        <Frame mode="home">
          <section className="mx-auto max-w-[900px] px-5 py-20 sm:px-8 lg:px-12">
            <p className="ww-kicker text-[#9b4a36]">Archive connection</p>
            <h1 className="ww-display mt-4 text-5xl text-[#263b32]">The shelves are out of reach.</h1>
            <p className="mt-4 max-w-lg text-sm leading-6 text-[#657168]">{describeError(account.error, 'We could not check your account just now.')}</p>
            <button className="ww-button mt-8 border border-[#294238] px-5 py-3 text-sm font-semibold text-[#294238] hover:bg-[#294238] hover:text-[#f7f2e7]" onClick={() => void account.refetch()} data-testid="button-retry-account">Try again</button>
          </section>
        </Frame>
      );
    }
  }

  if (!account.data) {
    return (
      <Frame mode="home">
        <section className="mx-auto max-w-[1120px] px-5 py-16 sm:px-8 sm:py-24 lg:px-12">
          <div className="ww-entrance max-w-[780px]">
            <p className="ww-kicker flex items-center gap-3 text-[#9b4a36]"><span className="h-px w-9 bg-[#a4523b]" /> A private world-building archive</p>
            <h1 className="ww-display mt-6 text-[clamp(4rem,9vw,8.8rem)] leading-[.82] text-[#263b32]">Make room<br />for <em className="text-[#a4523b]">wonder.</em></h1>
            <p className="mt-8 max-w-[500px] text-[16px] leading-7 text-[#657168]">Keep the details that make an imagined world feel inevitable: its names, customs, boundaries, old stories, and quiet contradictions.</p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Link href="/register" className="ww-button inline-flex items-center gap-4 bg-[#294238] px-5 py-3.5 text-[13px] font-semibold text-[#f7f2e7] no-underline hover:bg-[#38574a]" data-testid="link-home-register">Create your account <ArrowRight size={16} /></Link>
              <Link href="/login" className="inline-flex items-center gap-2 border border-[#bdb4a3] px-5 py-3.5 text-[13px] font-semibold text-[#34473d] no-underline hover:bg-[#f5f0e5]" data-testid="link-home-login">Sign in <ArrowDownRight size={15} /></Link>
            </div>
          </div>
          <div className="mt-16 grid max-w-[990px] grid-cols-1 border-y border-[#d8d0c1] sm:grid-cols-3">
            {[
              ['01', 'Keep it coherent', 'A place for details to find one another.'],
              ['02', 'Keep it yours', 'A self-hosted home for your own canon.'],
              ['03', 'Begin with a name', 'The archive starts when you do.'],
            ].map(([number, title, text]) => (
              <div key={number} className="flex gap-4 border-b border-[#d8d0c1] py-5 sm:border-b-0 sm:border-r sm:px-5 sm:first:pl-0 sm:last:border-r-0">
                <span className="ww-kicker pt-1 text-[#a4523b]">{number}</span>
                <div><h2 className="ww-display text-[21px] text-[#33483e]">{title}</h2><p className="mt-1 text-[12px] leading-5 text-[#788078]">{text}</p></div>
              </div>
            ))}
          </div>
          <p className="mt-6 ww-kicker text-[9px] text-[#83877e]" data-testid="status-first-run">Signed out · No account loaded</p>
        </section>
      </Frame>
    );
  }

  const profile = account.data;
  const created = new Date(profile.created_at);
  const createdLabel = Number.isNaN(created.getTime()) ? 'Date unavailable' : new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'long', day: 'numeric' }).format(created);
  return (
    <Frame mode="home">
      <section className="mx-auto max-w-[1120px] px-5 py-12 sm:px-8 sm:py-16 lg:px-12 lg:py-20">
        <div className="ww-entrance flex flex-col justify-between gap-7 border-b border-[#d8d0c1] pb-9 sm:flex-row sm:items-end">
          <div>
            <p className="ww-kicker flex items-center gap-3 text-[#9b4a36]"><span className="h-px w-9 bg-[#a4523b]" /> Private archive / home</p>
            <h1 className="ww-display mt-5 text-[clamp(3.4rem,7vw,6.4rem)] leading-[.9] text-[#263b32]">Good to see you,<br /><em className="text-[#a4523b]">{profile.display_name}.</em></h1>
            <p className="mt-5 text-[14px] leading-6 text-[#657168]">Your workspace is ready. The first page is still yours to write.</p>
          </div>
          <button
            className="ww-button inline-flex items-center gap-2 self-start border border-[#c9c1b2] px-4 py-2.5 text-[12px] font-semibold text-[#48574d] hover:border-[#9b4a36] hover:text-[#9b4a36] sm:self-auto"
            onClick={signOut}
            disabled={logout.isPending}
            data-testid="button-logout"
          >{logout.isPending ? 'Signing out…' : 'Sign out'} <LogOut size={14} /></button>
        </div>
        {logoutError && <p className="mt-4 text-sm text-[#9b4a36]" role="alert" data-testid="status-logout-error">{logoutError}</p>}

        <div className="mt-8 grid gap-6 lg:grid-cols-[1.55fr_.8fr]">
          <div className="space-y-6">
            {/* Create Universe Form / Banner */}
            <div className="border border-[#d9d1c2] bg-[#f8f4e9] p-6 sm:p-7">
              <div className="flex items-center justify-between border-b border-[#ded7ca] pb-3">
                <p className="ww-kicker text-[#9b4a36]">Canon Archives</p>
                <button
                  onClick={() => setShowCreateForm(!showCreateForm)}
                  className="ww-button inline-flex items-center gap-1.5 border border-[#294238] bg-[#294238] px-3 py-1.5 text-xs font-semibold text-[#f7f2e7] hover:bg-[#38574a]"
                  data-testid="button-toggle-create-universe"
                >
                  <BookOpen size={13} /> {showCreateForm ? 'Close form' : '+ New Universe'}
                </button>
              </div>

              {showCreateForm && (
                <form onSubmit={handleCreateUniverse} className="mt-5 space-y-4 rounded border border-[#ded7ca] bg-white/70 p-5" data-testid="form-create-universe">
                  <h3 className="font-serif text-lg text-[#253a32]">Create a New Universe</h3>
                  <div>
                    <label className="block text-xs font-semibold text-[#34473d]">Universe Name</label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Eldoria, The Astral Frontier"
                      value={newUniName}
                      onChange={(e) => setNewUniName(e.target.value)}
                      className="mt-1 w-full rounded border border-[#d5cebf] bg-[#faf7ef] px-3 py-2 text-xs text-[#253a32] focus:border-[#9b4a36] focus:outline-none"
                      data-testid="input-universe-name"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-[#34473d]">Description (optional)</label>
                    <textarea
                      rows={2}
                      placeholder="A short premise or setting summary..."
                      value={newUniDesc}
                      onChange={(e) => setNewUniDesc(e.target.value)}
                      className="mt-1 w-full rounded border border-[#d5cebf] bg-[#faf7ef] px-3 py-2 text-xs text-[#253a32] focus:border-[#9b4a36] focus:outline-none"
                      data-testid="input-universe-desc"
                    />
                  </div>
                  {createError && (
                    <p className="text-xs text-[#9b4a36]" role="alert">{createError}</p>
                  )}
                  <div className="flex gap-2 pt-1">
                    <button
                      type="submit"
                      disabled={createUniverse.isPending}
                      className="ww-button bg-[#294238] px-4 py-2 text-xs font-semibold text-[#f7f2e7] hover:bg-[#38574a]"
                      data-testid="button-submit-create-universe"
                    >
                      {createUniverse.isPending ? 'Creating…' : 'Create Universe'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowCreateForm(false)}
                      className="border border-[#c9c1b2] px-3 py-2 text-xs text-[#53655b]"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}

              {/* Universes List */}
              {universeList?.items && universeList.items.length > 0 ? (
                <div className="mt-5 space-y-3" data-testid="list-universes">
                  {universeList.items.map((u: UniverseResponse) => (
                    <div
                      key={u.id}
                      className="flex flex-col justify-between gap-4 border border-[#ded7ca] bg-white/70 p-4 transition-all hover:border-[#9b4a36] hover:shadow-sm sm:flex-row sm:items-center"
                      data-testid={`card-universe-${u.id}`}
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-serif text-lg font-medium text-[#253a32]">{u.name}</h3>
                          <span className="rounded bg-[#294238]/10 px-2 py-0.5 text-[10px] font-semibold text-[#294238] capitalize">
                            {u.role}
                          </span>
                          <span className="rounded bg-[#ded7ca]/50 px-1.5 py-0.5 text-[10px] text-[#6e786f] uppercase">
                            {u.status}
                          </span>
                        </div>
                        {u.description && (
                          <p className="mt-1 line-clamp-2 text-xs text-[#657168]">{u.description}</p>
                        )}
                        <span className="mt-1 block font-mono text-[10px] text-[#899087]">folio: {u.slug}</span>
                      </div>
                      <Link
                        href={`/universes/${u.id}`}
                        className="ww-button inline-flex items-center gap-1.5 self-start border border-[#294238] px-3.5 py-2 text-xs font-semibold text-[#294238] hover:bg-[#294238] hover:text-[#f7f2e7] sm:self-auto"
                        data-testid={`link-enter-universe-${u.id}`}
                      >
                        Enter Archive <ArrowRight size={13} />
                      </Link>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-5 text-center py-8">
                  <p className="font-serif text-2xl text-[#30463b]">An atlas begins with a blank leaf.</p>
                  <p className="mt-2 text-xs text-[#68746a]">There are no universes in this workspace yet. Create your first canon to begin.</p>
                  {!showCreateForm && (
                    <button
                      onClick={() => setShowCreateForm(true)}
                      className="ww-button mt-4 inline-flex items-center gap-2 bg-[#294238] px-4 py-2 text-xs font-semibold text-[#f7f2e7] hover:bg-[#38574a]"
                    >
                      <Plus size={14} /> Create your first universe
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
          <aside className="border border-[#d9d1c2] bg-[#f7f3e9]/75 p-6 sm:p-7">
            <div className="flex items-center justify-between border-b border-[#ded7ca] pb-4">
              <p className="ww-kicker text-[#9b4a36]">Account record</p><Check size={15} className="text-[#63836a]" />
            </div>
            <dl className="mt-2">
              <div className="border-b border-[#e2dccf] py-4">
                <dt className="ww-kicker !text-[9px] text-[#899087]">Display name</dt>
                <dd className="mt-1 text-[14px] font-medium text-[#34473d]" data-testid="text-account-name">{profile.display_name}</dd>
              </div>
              <div className="border-b border-[#e2dccf] py-4">
                <dt className="ww-kicker !text-[9px] text-[#899087]">Email address</dt>
                <dd className="mt-1 break-all text-[13px] text-[#526158]" data-testid="text-account-email">{profile.email}</dd>
              </div>
              <div className="py-4">
                <dt className="ww-kicker !text-[9px] text-[#899087]">Joined this archive</dt>
                <dd className="mt-1 text-[13px] text-[#526158]" data-testid="text-account-created">{createdLabel}</dd>
              </div>
            </dl>
            <div className="mt-1 flex items-start gap-2 border-t border-[#ded7ca] pt-4 text-[11px] leading-5 text-[#788078]">
              <ShieldCheck size={14} className="mt-0.5 shrink-0 text-[#64856b]" />
              <span>Session active on this self-hosted instance.</span>
            </div>
          </aside>
        </div>
        <div className="mt-6 flex flex-col justify-between gap-2 text-[11px] text-[#879087] sm:flex-row">
          <span data-testid="text-account-id">Account reference · {profile.id}</span>
          <span>Later chapters will appear here when they are ready.</span>
        </div>
      </section>
    </Frame>
  );
}

function Router() {
  return (
    <RoutedErrorBoundary>
      <Switch>
        <Route path="/" component={AccountHome} />
        <Route path="/register"><AuthPage register /></Route>
        <Route path="/login"><AuthPage /></Route>
        <Route path="/universes/:id"><Frame mode="home"><UniverseDetail /></Frame></Route>
        <Route component={NotFound} />
      </Switch>
    </RoutedErrorBoundary>
  );
}

function RoutedErrorBoundary({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}>{children}</ErrorBoundary>;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
          <Router />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
