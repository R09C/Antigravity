using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using System;

public class Ronin : MonoBehaviour
{
    [Header("Movement")]
    public float moveSpeed = 5f;

    [Header("Combat - Gaussian Aura")]
    public float maxAuraRange = 10f;
    [Tooltip("Standard deviation for the Gaussian aura. Lower means sharper/narrower effect, higher means wider effect.")]
    public float auraSigma = 1f;
    public float baseAuraDamage = 10f;

    private float currentDirection = 1f; // 1 for right, -1 for left

    void Update()
    {
        HandleMovement();
        HandleAuraCombat();
    }

    private void HandleMovement()
    {
        // 1D Movement along the X axis
        float horizontalInput = Input.GetAxisRaw("Horizontal");

        if (horizontalInput != 0)
        {
            currentDirection = Mathf.Sign(horizontalInput);
            transform.position += new Vector3(horizontalInput * moveSpeed * Time.deltaTime, 0, 0);

            // Flip the sprite visually if needed (assuming SpriteRenderer handles this or scaling)
            Vector3 scale = transform.localScale;
            scale.x = Mathf.Abs(scale.x) * currentDirection;
            transform.localScale = scale;
        }
    }

    private void HandleAuraCombat()
    {
        // Trigger aura with space or click
        if (Input.GetKeyDown(KeyCode.Space))
        {
            ApplyGaussianAura();
        }
    }

    public void ChangeAuraSigma(float newSigma)
    {
        // Allow modifying the variance/sigma dynamically through 'stances'
        auraSigma = Mathf.Max(0.1f, newSigma); // Prevent division by zero
        Debug.Log($"Aura sigma changed to: {auraSigma}");
    }

    private void ApplyGaussianAura()
    {
        // This is a conceptual implementation of applying a Gaussian mathematical function
        // to enemies based solely on their 1D X-axis distance.
        // It avoids physics colliders completely.

        // Assuming a global 'EnemyManager' or similar that holds a list of enemies,
        // we'd iterate through them here. Since we don't have one, we'll demonstrate the math.

        Debug.Log($"Applying Gaussian Aura centered at X: {transform.position.x} with Sigma: {auraSigma}");

        // In a real scenario, you would fetch all enemies:
        // foreach(Enemy enemy in EnemyManager.ActiveEnemies)
        // {
        //     float distanceX = enemy.transform.position.x - transform.position.x;
        //     if (Mathf.Abs(distanceX) <= maxAuraRange)
        //     {
        //         float damage = CalculateGaussianDamage(distanceX);
        //         enemy.TakeDamage(damage);
        //     }
        // }
    }

    public float CalculateGaussianDamage(float distanceX)
    {
        // Gaussian function: f(x) = a * exp(-(x - b)^2 / (2 * c^2))
        // Where:
        // a = peak value (baseAuraDamage)
        // b = center (0, since we use distance from player)
        // c = standard deviation (auraSigma)

        float exponent = -(distanceX * distanceX) / (2f * auraSigma * auraSigma);
        float damageMultiplier = Mathf.Exp(exponent);
        return baseAuraDamage * damageMultiplier;
    }
}
