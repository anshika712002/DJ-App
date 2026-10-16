import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../src/session.dart';
import '../theme/app_theme.dart';
import '../widgets/artwork.dart';
import '../widgets/feedback.dart';
import 'signup_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _identifier = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  bool _obscure = true;

  @override
  void dispose() {
    _identifier.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _busy = true);
    final session = context.read<Session>();
    try {
      await session.login(
        identifier: _identifier.text.trim(),
        password: _password.text,
      );
      // A successful login flips Session.isAuthenticated; RootScreen routes the
      // user into the app shell.
    } catch (e) {
      if (!mounted) return;
      showApiError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: DecoratedBox(
        decoration: const BoxDecoration(gradient: AppColors.glowGradient),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 440),
                child: Card(
                  child: Padding(
                    padding: const EdgeInsets.all(AppSpacing.lg),
                    child: Form(
                      key: _formKey,
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          const Center(
                            child: _BrandMark(),
                          ),
                          const SizedBox(height: AppSpacing.md),
                          Text(
                            'Music Mixer',
                            textAlign: TextAlign.center,
                            style: theme.textTheme.headlineMedium,
                          ),
                          Text(
                            'Search songs, build a mix and play it',
                            textAlign: TextAlign.center,
                            style: theme.textTheme.bodyMedium
                                ?.copyWith(color: AppColors.textSecondary),
                          ),
                          const SizedBox(height: AppSpacing.xl),
                          TextFormField(
                            controller: _identifier,
                            keyboardType: TextInputType.emailAddress,
                            autofillHints: const [AutofillHints.username],
                            decoration: const InputDecoration(
                              labelText: 'Email or phone',
                              prefixIcon: Icon(Icons.person_outline),
                            ),
                            validator: (v) => (v == null || v.trim().isEmpty)
                                ? 'Enter your email or phone'
                                : null,
                          ),
                          const SizedBox(height: AppSpacing.md),
                          TextFormField(
                            controller: _password,
                            obscureText: _obscure,
                            autofillHints: const [AutofillHints.password],
                            decoration: InputDecoration(
                              labelText: 'Password',
                              prefixIcon: const Icon(Icons.lock_outline),
                              suffixIcon: IconButton(
                                icon: Icon(_obscure
                                    ? Icons.visibility_outlined
                                    : Icons.visibility_off_outlined),
                                onPressed: () =>
                                    setState(() => _obscure = !_obscure),
                              ),
                            ),
                            validator: (v) => (v == null || v.isEmpty)
                                ? 'Enter your password'
                                : null,
                            onFieldSubmitted: (_) => _submit(),
                          ),
                          const SizedBox(height: AppSpacing.lg),
                          FilledButton(
                            onPressed: _busy ? null : _submit,
                            child: _busy
                                ? const SizedBox(
                                    width: 20,
                                    height: 20,
                                    child:
                                        CircularProgressIndicator(strokeWidth: 2),
                                  )
                                : const Text('Sign in'),
                          ),
                          const SizedBox(height: AppSpacing.sm),
                          TextButton(
                            onPressed: _busy
                                ? null
                                : () => Navigator.of(context).push(
                                      MaterialPageRoute(
                                          builder: (_) => const SignupScreen()),
                                    ),
                            child: const Text('New here? Create an account'),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _BrandMark extends StatelessWidget {
  const _BrandMark();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 84,
      height: 84,
      decoration: const BoxDecoration(
        gradient: AppColors.brandGradient,
        shape: BoxShape.circle,
        boxShadow: [
          BoxShadow(color: Color(0x66A855F7), blurRadius: 28, spreadRadius: 2),
        ],
      ),
      child: const Center(child: EqualizerBars(size: 38)),
    );
  }
}
