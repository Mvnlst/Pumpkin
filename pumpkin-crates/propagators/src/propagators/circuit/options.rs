// the approach used to the circuit constraint
#[derive(Debug, Default, Clone, Copy, PartialEq)]
#[cfg_attr(feature = "clap", derive(clap::ValueEnum))]
pub enum CircuitPropagationMethod {
    // Use the baseline circuit propagator
    #[default]
    Base,
    // Enable strong bridge detection
    StrongBridges,
}